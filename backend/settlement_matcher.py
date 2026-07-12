from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from backend.alias_repository import find_active_alias, get_connection
from backend.candidate_generator import Candidate, generate_candidates
from backend.confidence_scorer import (
    ConfidenceResult,
    composite_confidence,
    determine_match_status,
    historical_evidence_score,
    rejection_penalty,
)
from backend.confidence_scorer import ADMIN_CONTRADICTION_THRESHOLD
from backend.llm_reviewer import request_reasoning_note
from backend.review_repository import get_rejection_count
from backend.spatial_matcher import SpatialEvidence, evaluate_spatial_evidence
from backend.text_normalizer import normalize_place_name
from backend.utils import coordinate_masks, detect_column_map, ensure_gazetteer_ids

ProgressCallback = Callable[[int, int, str], None]
OllamaCache = dict[tuple[str, str, str, str], "str | None"]

_SENTENCE_MODEL = None
_CANDIDATE_LIMIT = 5

# Legacy field names are kept first (and populated) so the existing frontend,
# geocoder.apply_geocodes, and exporters keep working unmodified; the
# Place Intelligence Engine upgrade's expanded fields are appended alongside
# them rather than replacing them. "confidence"/"overall_confidence",
# "status"/"decision_status", "latitude"/"official_latitude", and
# "suggested_district"/"official_district" (etc.) are intentionally
# duplicate views of the same value for backward compatibility.
MATCH_COLUMNS = [
    "record_id",
    "source_row",
    "submitted_settlement",
    "submitted_district",
    "submitted_region",
    "submitted_latitude",
    "submitted_longitude",
    "suggested_settlement",
    "suggested_district",
    "suggested_region",
    "latitude",
    "longitude",
    "confidence",
    "matching_method",
    "reason",
    "status",
    "accept",
    "reject",
    "run_id",
    "normalized_submitted_settlement",
    "suggested_gazetteer_id",
    "official_district",
    "official_region",
    "official_latitude",
    "official_longitude",
    "overall_confidence",
    "name_score",
    "district_score",
    "region_score",
    "semantic_score",
    "spatial_score",
    "historical_score",
    "rejection_penalty",
    "distance_km",
    "candidate_rank",
    "decision_status",
    "llm_note",
    "reviewer",
    "reviewed_at",
]


@dataclass
class PreparedGazetteer:
    data: pd.DataFrame
    columns: dict[str, str | None]


def _prepare_gazetteer(gazetteer_df: pd.DataFrame) -> PreparedGazetteer:
    columns = detect_column_map(gazetteer_df)
    data = ensure_gazetteer_ids(gazetteer_df, columns)
    columns = detect_column_map(data)
    for field in ("settlement", "district", "region"):
        column = columns.get(field)
        data[f"_{field}_norm"] = data[column].map(normalize_place_name) if column else ""
    settlement_col = columns.get("settlement")
    district_col = columns.get("district")
    region_col = columns.get("region")
    data["_candidate_text"] = data[settlement_col].fillna("").astype(str) if settlement_col else ""
    if district_col:
        data["_candidate_text"] += " " + data[district_col].fillna("").astype(str)
    if region_col:
        data["_candidate_text"] += " " + data[region_col].fillna("").astype(str)
    data["_candidate_text"] = data["_candidate_text"].map(normalize_place_name)
    return PreparedGazetteer(data=data, columns=columns)


def _get_sentence_model():
    """Load the embedding model once and reuse it for every match_records() call."""
    global _SENTENCE_MODEL
    if _SENTENCE_MODEL is None:
        from sentence_transformers import SentenceTransformer

        _SENTENCE_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _SENTENCE_MODEL


def _is_ambiguous_national_name(
    prepared: PreparedGazetteer,
    settlement_norm: str,
    submitted_district_norm: str,
    submitted_region_norm: str,
) -> bool:
    """True when a settlement name exists in multiple districts nationally
    and there is no submitted district/region evidence to disambiguate it."""
    if submitted_district_norm or submitted_region_norm:
        return False
    matches = prepared.data[prepared.data["_settlement_norm"] == settlement_norm]
    return matches["_district_norm"].nunique(dropna=True) > 1


def _empty_row(
    record_id: int,
    source_row: object,
    submitted_settlement: object,
    submitted_district: object,
    submitted_region: object,
    submitted_latitude: object,
    submitted_longitude: object,
    run_id: str,
    reason: str,
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "source_row": source_row,
        "submitted_settlement": submitted_settlement,
        "submitted_district": submitted_district,
        "submitted_region": submitted_region,
        "submitted_latitude": submitted_latitude,
        "submitted_longitude": submitted_longitude,
        "suggested_settlement": "",
        "suggested_district": "",
        "suggested_region": "",
        "latitude": None,
        "longitude": None,
        "confidence": 0.0,
        "matching_method": "none",
        "reason": reason,
        "status": "unresolved",
        "accept": False,
        "reject": False,
        "run_id": run_id,
        "normalized_submitted_settlement": normalize_place_name(submitted_settlement, strip_generic_suffixes=True),
        "suggested_gazetteer_id": "",
        "official_district": "",
        "official_region": "",
        "official_latitude": None,
        "official_longitude": None,
        "overall_confidence": 0.0,
        "name_score": None,
        "district_score": None,
        "region_score": None,
        "semantic_score": None,
        "spatial_score": None,
        "historical_score": None,
        "rejection_penalty": 0.0,
        "distance_km": None,
        "candidate_rank": None,
        "decision_status": "unresolved",
        "llm_note": None,
        "reviewer": None,
        "reviewed_at": None,
    }


def _empty_matches() -> pd.DataFrame:
    return pd.DataFrame(columns=MATCH_COLUMNS)


def _score_candidate(
    candidate: Candidate,
    *,
    submitted_district: object,
    submitted_latitude: float | None,
    submitted_longitude: float | None,
    normalized_submitted_settlement: str,
    submitted_district_norm: str,
    submitted_region_norm: str,
    conn,
    boundary_gdf,
    boundary_district_column: str | None,
) -> tuple[ConfidenceResult, SpatialEvidence, int, int]:
    spatial_evidence = evaluate_spatial_evidence(
        submitted_latitude,
        submitted_longitude,
        candidate.latitude,
        candidate.longitude,
        submitted_district,
        candidate.district,
        boundary_gdf,
        boundary_district_column,
    )

    approval_count = 0
    rejection_count = 0
    if conn is not None:
        alias_row = find_active_alias(conn, normalized_submitted_settlement, submitted_district_norm, submitted_region_norm)
        if alias_row is not None and str(alias_row.get("official_gazetteer_id", "")) == candidate.gazetteer_id:
            approval_count = int(alias_row.get("approval_count", 0))
        rejection_count = get_rejection_count(
            conn, normalized_submitted_settlement, submitted_district_norm, submitted_region_norm, candidate.gazetteer_id
        )

    historical_score = historical_evidence_score(approval_count)
    penalty = rejection_penalty(rejection_count)
    confidence_result = composite_confidence(
        name_score=candidate.name_score,
        district_score=candidate.district_score,
        region_score=candidate.region_score,
        spatial_score=spatial_evidence.spatial_score,
        historical_score=historical_score,
        semantic_score=candidate.semantic_score,
        rejection_penalty_value=penalty,
    )
    return confidence_result, spatial_evidence, approval_count, rejection_count


def _build_match_row(
    *,
    record_id: int,
    source_row: object,
    run_id: str,
    submitted_settlement: object,
    submitted_district: object,
    submitted_region: object,
    submitted_latitude: float | None,
    submitted_longitude: float | None,
    prepared: PreparedGazetteer,
    conn,
    boundary_gdf,
    boundary_district_column: str | None,
    semantic_model,
    gazetteer_embeddings,
    use_ollama: bool,
    ollama_cache: OllamaCache,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    normalized_submitted_settlement = normalize_place_name(submitted_settlement, strip_generic_suffixes=True)
    if not normalized_submitted_settlement:
        return _empty_row(
            record_id, source_row, submitted_settlement, submitted_district, submitted_region,
            submitted_latitude, submitted_longitude, run_id, "Settlement name is missing.",
        ), []

    submitted_district_norm = normalize_place_name(submitted_district)
    submitted_region_norm = normalize_place_name(submitted_region)

    def alias_lookup(name_norm: str, district_norm: str, region_norm: str):
        if conn is None:
            return None
        return find_active_alias(conn, name_norm, district_norm, region_norm)

    candidates = generate_candidates(
        submitted_settlement=submitted_settlement,
        submitted_district=submitted_district,
        submitted_region=submitted_region,
        prepared_gazetteer=prepared.data,
        columns=prepared.columns,
        alias_lookup=alias_lookup,
        semantic_model=semantic_model,
        gazetteer_embeddings=gazetteer_embeddings,
        top_n=_CANDIDATE_LIMIT,
    )

    if not candidates:
        return _empty_row(
            record_id, source_row, submitted_settlement, submitted_district, submitted_region,
            submitted_latitude, submitted_longitude, run_id, "No viable gazetteer candidate was found.",
        ), []

    scored = [
        (
            candidate,
            *_score_candidate(
                candidate,
                submitted_district=submitted_district,
                submitted_latitude=submitted_latitude,
                submitted_longitude=submitted_longitude,
                normalized_submitted_settlement=normalized_submitted_settlement,
                submitted_district_norm=submitted_district_norm,
                submitted_region_norm=submitted_region_norm,
                conn=conn,
                boundary_gdf=boundary_gdf,
                boundary_district_column=boundary_district_column,
            ),
        )
        for candidate in candidates
    ]
    # Re-rank by the full composite confidence (spatial/historical/semantic
    # evidence can outweigh a slightly lower name_score), not just the
    # candidate generator's initial name-similarity ordering.
    scored.sort(key=lambda item: item[1].overall_confidence, reverse=True)
    for rank, item in enumerate(scored, start=1):
        item[0].rank = rank

    top_candidate, top_confidence, top_spatial, top_approvals, top_rejections = scored[0]
    is_ambiguous = _is_ambiguous_national_name(
        prepared, normalize_place_name(top_candidate.settlement), submitted_district_norm, submitted_region_norm
    )
    second_confidence = scored[1][1].overall_confidence if len(scored) > 1 else None
    candidate_missing_admin_info = not top_candidate.district and not top_candidate.region

    safety = determine_match_status(
        confidence=top_confidence.overall_confidence,
        district_score=top_confidence.district_score,
        region_score=top_confidence.region_score,
        is_ambiguous_national_name=is_ambiguous,
        spatial_distance_km=top_spatial.distance_km,
        second_candidate_confidence=second_confidence,
        rejection_count=top_rejections,
        candidate_missing_admin_info=candidate_missing_admin_info,
    )

    reason = f"{top_candidate.matching_method.replace('_', ' ').title()} match. {top_confidence.explanation}"
    if safety.blocked_reasons:
        reason += f" Held for review: {', '.join(safety.blocked_reasons)}."

    # Shared candidate comparison list - used both as the Ollama evidence
    # payload below and returned to the caller so the review UI can show a
    # real top-5 comparison instead of just the single winning candidate.
    candidate_list = [
        {
            "rank": c.rank,
            "gazetteer_id": c.gazetteer_id,
            "settlement": c.settlement,
            "district": c.district,
            "region": c.region,
            "latitude": c.latitude,
            "longitude": c.longitude,
            "matching_method": c.matching_method,
            "name_score": c.name_score,
            "semantic_score": conf.semantic_score,
            "spatial_score": conf.spatial_score,
            "historical_score": conf.historical_score,
            "distance_km": spatial_ev.distance_km,
            "overall_confidence": conf.overall_confidence,
            "approval_count": approvals,
            "rejection_count": rejections,
            "admin_conflict": (
                (conf.district_score is not None and conf.district_score < ADMIN_CONTRADICTION_THRESHOLD)
                or (conf.region_score is not None and conf.region_score < ADMIN_CONTRADICTION_THRESHOLD)
            ),
        }
        for c, conf, spatial_ev, approvals, rejections in scored
    ]

    llm_note = None
    if use_ollama and safety.status == "needs_review":
        cache_key = (
            normalized_submitted_settlement,
            submitted_district_norm,
            submitted_region_norm,
            top_candidate.gazetteer_id,
        )
        if cache_key in ollama_cache:
            llm_note = ollama_cache[cache_key]
        else:
            llm_note = request_reasoning_note(
                submitted_settlement=submitted_settlement,
                submitted_district=submitted_district,
                submitted_region=submitted_region,
                submitted_latitude=submitted_latitude,
                submitted_longitude=submitted_longitude,
                candidates=candidate_list,
            )
            ollama_cache[cache_key] = llm_note
        if llm_note:
            reason = f"{reason} Local AI note: {llm_note}"

    row = {
        "record_id": record_id,
        "source_row": source_row,
        "submitted_settlement": submitted_settlement,
        "submitted_district": submitted_district,
        "submitted_region": submitted_region,
        "submitted_latitude": submitted_latitude,
        "submitted_longitude": submitted_longitude,
        "suggested_settlement": top_candidate.settlement,
        "suggested_district": top_candidate.district,
        "suggested_region": top_candidate.region,
        "latitude": top_candidate.latitude,
        "longitude": top_candidate.longitude,
        "confidence": top_confidence.overall_confidence,
        "matching_method": top_candidate.matching_method,
        "reason": reason,
        "status": safety.status,
        "accept": safety.status == "auto_accepted",
        "reject": False,
        "run_id": run_id,
        "normalized_submitted_settlement": normalized_submitted_settlement,
        "suggested_gazetteer_id": top_candidate.gazetteer_id,
        "official_district": top_candidate.district,
        "official_region": top_candidate.region,
        "official_latitude": top_candidate.latitude,
        "official_longitude": top_candidate.longitude,
        "overall_confidence": top_confidence.overall_confidence,
        "name_score": top_candidate.name_score,
        "district_score": top_confidence.district_score,
        "region_score": top_confidence.region_score,
        "semantic_score": top_confidence.semantic_score,
        "spatial_score": top_confidence.spatial_score,
        "historical_score": top_confidence.historical_score,
        "rejection_penalty": top_confidence.rejection_penalty,
        "distance_km": top_spatial.distance_km,
        "candidate_rank": top_candidate.rank,
        "decision_status": safety.status,
        "llm_note": llm_note,
        "reviewer": None,
        "reviewed_at": None,
    }
    return row, candidate_list


def match_records(
    response_df: pd.DataFrame,
    gazetteer_df: pd.DataFrame,
    use_semantic: bool = False,
    use_ollama: bool = False,
    progress_callback: ProgressCallback | None = None,
    boundary_gdf=None,
) -> tuple[pd.DataFrame, dict[int, list[dict[str, object]]]]:
    """Match response records missing coordinates against the gazetteer.

    Returns (matches_df, candidates_by_record): candidates_by_record maps
    each matched record_id to its full ranked candidate shortlist (not just
    the winner in matches_df), so the review UI can show a real top-N
    comparison instead of only the single suggestion.
    """
    response_columns = detect_column_map(response_df)
    prepared = _prepare_gazetteer(gazetteer_df)

    required_gazetteer = ["settlement", "latitude", "longitude"]
    if any(not prepared.columns.get(field) for field in required_gazetteer):
        return _empty_matches(), {}

    missing_mask, invalid_mask, _ = coordinate_masks(
        response_df,
        response_columns.get("latitude"),
        response_columns.get("longitude"),
    )
    records_to_match = response_df[missing_mask | invalid_mask].copy()
    if records_to_match.empty:
        return _empty_matches(), {}

    settlement_col = response_columns.get("settlement")
    district_col = response_columns.get("district")
    region_col = response_columns.get("region")
    lat_col = response_columns.get("latitude")
    lon_col = response_columns.get("longitude")
    source_row_col = "_source_row_id" if "_source_row_id" in response_df.columns else None

    boundary_district_column = None
    if boundary_gdf is not None and hasattr(boundary_gdf, "columns"):
        boundary_columns = detect_column_map(boundary_gdf)
        boundary_district_column = boundary_columns.get("district")

    # Load the embedding model once and embed the whole gazetteer once, instead of
    # reloading the model and re-encoding candidates on every row.
    semantic_model = None
    gazetteer_embeddings = None
    if use_semantic:
        try:
            semantic_model = _get_sentence_model()
            gazetteer_embeddings = semantic_model.encode(
                prepared.data["_candidate_text"].fillna("").tolist(),
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except (ImportError, OSError, RuntimeError):
            # Model package missing, or the pretrained weights/config failed to
            # download or load (flaky network, Hub outage, etc.) - degrade to
            # RapidFuzz-only matching instead of crashing the whole run.
            semantic_model = None
            gazetteer_embeddings = None

    run_id = str(uuid.uuid4())
    ollama_cache: OllamaCache = {}
    total = len(records_to_match)
    conn = get_connection()
    try:
        matches = []
        candidates_by_record: dict[int, list[dict[str, object]]] = {}
        for position, (record_id, row) in enumerate(records_to_match.iterrows(), start=1):
            submitted_settlement = row.get(settlement_col, "") if settlement_col else ""
            submitted_district = row.get(district_col, "") if district_col else ""
            submitted_region = row.get(region_col, "") if region_col else ""
            submitted_latitude = row.get(lat_col) if lat_col else None
            submitted_longitude = row.get(lon_col) if lon_col else None
            if pd.isna(submitted_latitude):
                submitted_latitude = None
            if pd.isna(submitted_longitude):
                submitted_longitude = None
            source_row = row.get(source_row_col, record_id + 2) if source_row_col else record_id + 2

            if progress_callback:
                progress_callback(position, total, f"Matching {submitted_settlement or 'record'}")

            match_row, candidate_list = _build_match_row(
                record_id=int(record_id),
                source_row=source_row,
                run_id=run_id,
                submitted_settlement=submitted_settlement,
                submitted_district=submitted_district,
                submitted_region=submitted_region,
                submitted_latitude=submitted_latitude,
                submitted_longitude=submitted_longitude,
                prepared=prepared,
                conn=conn,
                boundary_gdf=boundary_gdf,
                boundary_district_column=boundary_district_column,
                semantic_model=semantic_model,
                gazetteer_embeddings=gazetteer_embeddings,
                use_ollama=use_ollama,
                ollama_cache=ollama_cache,
            )
            matches.append(match_row)
            if candidate_list:
                candidates_by_record[int(record_id)] = candidate_list
    finally:
        conn.close()

    return pd.DataFrame(matches, columns=MATCH_COLUMNS), candidates_by_record


def matching_statistics(matches_df: pd.DataFrame) -> dict[str, int | float]:
    if matches_df is None or matches_df.empty:
        return {
            "matched": 0,
            "auto_accepted": 0,
            "needs_review": 0,
            "unresolved": 0,
            "average_confidence": 0,
        }
    status = matches_df["status"].fillna("")
    return {
        "matched": int(status.isin(["auto_accepted", "accepted", "needs_review"]).sum()),
        "auto_accepted": int(status.isin(["auto_accepted", "accepted"]).sum()),
        "needs_review": int((status == "needs_review").sum()),
        "unresolved": int((status == "unresolved").sum()),
        "average_confidence": round(float(matches_df["confidence"].fillna(0).mean()), 1),
    }
