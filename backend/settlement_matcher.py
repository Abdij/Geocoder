from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from config import MATCH_AUTO_ACCEPT, MATCH_NEEDS_REVIEW
from backend.utils import coordinate_masks, detect_column_map, normalize_text

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - fallback used only without RapidFuzz installed.
    fuzz = None
    process = None


ProgressCallback = Callable[[int, int, str], None]
OllamaCache = dict[tuple[str, str, str, str], "str | None"]

_SENTENCE_MODEL = None


MATCH_COLUMNS = [
    "record_id",
    "source_row",
    "submitted_settlement",
    "submitted_district",
    "submitted_region",
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
]


@dataclass
class PreparedGazetteer:
    data: pd.DataFrame
    columns: dict[str, str | None]


def _similarity(left: object, right: object) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 60.0
    if left_norm == right_norm:
        return 100.0
    if fuzz is not None:
        return float(fuzz.WRatio(left_norm, right_norm))

    from difflib import SequenceMatcher

    return SequenceMatcher(None, left_norm, right_norm).ratio() * 100


def _admin_consistency(
    submitted_district: object,
    suggested_district: object,
    submitted_region: object,
    suggested_region: object,
) -> float:
    district_left = normalize_text(submitted_district)
    district_right = normalize_text(suggested_district)
    region_left = normalize_text(submitted_region)
    region_right = normalize_text(suggested_region)

    district_match = bool(district_left and district_left == district_right)
    region_match = bool(region_left and region_left == region_right)
    district_missing = not district_left or not district_right
    region_missing = not region_left or not region_right

    if district_match and (region_match or region_missing):
        return 100.0
    if district_match:
        return 85.0
    if region_match:
        return 65.0
    if district_missing and region_missing:
        return 70.0
    if district_missing or region_missing:
        return 45.0
    return 0.0


def calculate_confidence(
    submitted_settlement: object,
    suggested_settlement: object,
    submitted_district: object,
    suggested_district: object,
    submitted_region: object,
    suggested_region: object,
) -> tuple[float, dict[str, float]]:
    settlement_score = _similarity(submitted_settlement, suggested_settlement)
    district_score = _similarity(submitted_district, suggested_district)
    region_score = _similarity(submitted_region, suggested_region)
    admin_score = _admin_consistency(
        submitted_district,
        suggested_district,
        submitted_region,
        suggested_region,
    )
    confidence = (
        settlement_score * 0.50
        + district_score * 0.25
        + region_score * 0.15
        + admin_score * 0.10
    )
    components = {
        "settlement_similarity": round(settlement_score, 1),
        "district_similarity": round(district_score, 1),
        "region_similarity": round(region_score, 1),
        "administrative_consistency": round(admin_score, 1),
    }
    return round(float(confidence), 1), components


def _status_for_confidence(confidence: float) -> str:
    if confidence >= MATCH_AUTO_ACCEPT:
        return "auto_accepted"
    if confidence >= MATCH_NEEDS_REVIEW:
        return "needs_review"
    return "unresolved"


def _prepare_gazetteer(gazetteer_df: pd.DataFrame) -> PreparedGazetteer:
    columns = detect_column_map(gazetteer_df)
    data = gazetteer_df.copy()
    for field in ("settlement", "district", "region"):
        column = columns.get(field)
        data[f"_{field}_norm"] = data[column].map(normalize_text) if column else ""
    settlement_col = columns.get("settlement")
    district_col = columns.get("district")
    region_col = columns.get("region")
    data["_candidate_text"] = (
        data[settlement_col].fillna("").astype(str) if settlement_col else ""
    )
    if district_col:
        data["_candidate_text"] += " " + data[district_col].fillna("").astype(str)
    if region_col:
        data["_candidate_text"] += " " + data[region_col].fillna("").astype(str)
    data["_candidate_text"] = data["_candidate_text"].map(normalize_text)
    return PreparedGazetteer(data=data, columns=columns)


def _candidate_subset(
    prepared: PreparedGazetteer,
    submitted_district: object,
    submitted_region: object,
) -> pd.DataFrame:
    data = prepared.data
    district_norm = normalize_text(submitted_district)
    region_norm = normalize_text(submitted_region)
    if district_norm:
        district_candidates = data[data["_district_norm"] == district_norm]
        if not district_candidates.empty:
            return district_candidates
    if region_norm:
        region_candidates = data[data["_region_norm"] == region_norm]
        if not region_candidates.empty:
            return region_candidates
    return data


def _extract_top_candidates(query: str, candidates: pd.DataFrame, limit: int = 8) -> list[int]:
    if candidates.empty or not query:
        return []
    candidate_texts = candidates["_candidate_text"].fillna("").tolist()
    candidate_indices = candidates.index.tolist()

    if process is not None and fuzz is not None:
        extracted = process.extract(query, candidate_texts, scorer=fuzz.WRatio, limit=limit)
        return [candidate_indices[item[2]] for item in extracted if item[1] > 0]

    scored = [
        (idx, _similarity(query, text))
        for idx, text in zip(candidate_indices, candidate_texts, strict=False)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [idx for idx, score in scored[:limit] if score > 0]


def _get_sentence_model():
    """Load the embedding model once and reuse it for every match_records() call."""
    global _SENTENCE_MODEL
    if _SENTENCE_MODEL is None:
        from sentence_transformers import SentenceTransformer

        _SENTENCE_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _SENTENCE_MODEL


def _ollama_reason(
    submitted_settlement: object,
    submitted_district: object,
    candidate: pd.Series,
    prepared: PreparedGazetteer,
) -> str | None:
    try:
        import requests
    except ImportError:
        return None

    settlement_col = prepared.columns.get("settlement")
    district_col = prepared.columns.get("district")
    payload = {
        "model": "qwen2.5",
        "prompt": (
            "You are helping validate a humanitarian GIS settlement name match. "
            "Give one concise reason, no more than 25 words. "
            f"Submitted: {submitted_settlement}, district: {submitted_district}. "
            f"Suggested: {candidate.get(settlement_col, '')}, district: {candidate.get(district_col, '')}."
        ),
        "stream": False,
    }
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=8)
        response.raise_for_status()
        text = response.json().get("response", "").strip()
        return text[:240] if text else None
    except Exception:
        return None


def _empty_matches() -> pd.DataFrame:
    return pd.DataFrame(columns=MATCH_COLUMNS)


def _match_candidate_to_row(
    record_id: int,
    source_row: object,
    submitted_settlement: object,
    submitted_district: object,
    submitted_region: object,
    candidate: pd.Series | None,
    prepared: PreparedGazetteer,
    method: str,
    reason_prefix: str,
    use_ollama: bool = False,
    ollama_cache: OllamaCache | None = None,
) -> dict[str, object]:
    settlement_col = prepared.columns.get("settlement")
    district_col = prepared.columns.get("district")
    region_col = prepared.columns.get("region")
    lat_col = prepared.columns.get("latitude")
    lon_col = prepared.columns.get("longitude")

    if candidate is None:
        return {
            "record_id": record_id,
            "source_row": source_row,
            "submitted_settlement": submitted_settlement,
            "submitted_district": submitted_district,
            "submitted_region": submitted_region,
            "suggested_settlement": "",
            "suggested_district": "",
            "suggested_region": "",
            "latitude": np.nan,
            "longitude": np.nan,
            "confidence": 0.0,
            "matching_method": "none",
            "reason": "No viable gazetteer candidate was found.",
            "status": "unresolved",
            "accept": False,
            "reject": False,
        }

    suggested_settlement = candidate.get(settlement_col, "") if settlement_col else ""
    suggested_district = candidate.get(district_col, "") if district_col else ""
    suggested_region = candidate.get(region_col, "") if region_col else ""
    confidence, components = calculate_confidence(
        submitted_settlement,
        suggested_settlement,
        submitted_district,
        suggested_district,
        submitted_region,
        suggested_region,
    )
    status = _status_for_confidence(confidence)
    component_text = (
        f"Settlement {components['settlement_similarity']}%, "
        f"district {components['district_similarity']}%, "
        f"region {components['region_similarity']}%, "
        f"admin {components['administrative_consistency']}%."
    )
    reason = f"{reason_prefix} {component_text}"
    if use_ollama and status == "needs_review":
        cache_key = (
            normalize_text(submitted_settlement),
            normalize_text(submitted_district),
            normalize_text(suggested_settlement),
            normalize_text(suggested_district),
        )
        if ollama_cache is not None and cache_key in ollama_cache:
            ollama_text = ollama_cache[cache_key]
        else:
            ollama_text = _ollama_reason(
                submitted_settlement,
                submitted_district,
                candidate,
                prepared,
            )
            if ollama_cache is not None:
                ollama_cache[cache_key] = ollama_text
        if ollama_text:
            reason = f"{reason} Local AI note: {ollama_text}"

    return {
        "record_id": record_id,
        "source_row": source_row,
        "submitted_settlement": submitted_settlement,
        "submitted_district": submitted_district,
        "submitted_region": submitted_region,
        "suggested_settlement": suggested_settlement,
        "suggested_district": suggested_district,
        "suggested_region": suggested_region,
        "latitude": candidate.get(lat_col, np.nan) if lat_col else np.nan,
        "longitude": candidate.get(lon_col, np.nan) if lon_col else np.nan,
        "confidence": confidence,
        "matching_method": method,
        "reason": reason,
        "status": status,
        "accept": status == "auto_accepted",
        "reject": False,
    }


def match_records(
    response_df: pd.DataFrame,
    gazetteer_df: pd.DataFrame,
    use_semantic: bool = False,
    use_ollama: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> pd.DataFrame:
    response_columns = detect_column_map(response_df)
    prepared = _prepare_gazetteer(gazetteer_df)

    required_gazetteer = ["settlement", "latitude", "longitude"]
    if any(not prepared.columns.get(field) for field in required_gazetteer):
        return _empty_matches()

    missing_mask, invalid_mask, _ = coordinate_masks(
        response_df,
        response_columns.get("latitude"),
        response_columns.get("longitude"),
    )
    records_to_match = response_df[missing_mask | invalid_mask].copy()
    if records_to_match.empty:
        return _empty_matches()

    settlement_col = response_columns.get("settlement")
    district_col = response_columns.get("district")
    region_col = response_columns.get("region")
    source_row_col = "_source_row_id" if "_source_row_id" in response_df.columns else None

    # Load the embedding model once and embed the whole gazetteer once, instead of
    # reloading the model and re-encoding candidates on every row (the previous
    # per-row implementation was the dominant cost on large files).
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
        except ImportError:
            semantic_model = None
            gazetteer_embeddings = None

    candidate_subset_cache: dict[tuple[str, str], pd.DataFrame] = {}
    top_candidate_cache: dict[tuple[str, str, str], list[int]] = {}
    ollama_cache: OllamaCache = {}

    total = len(records_to_match)
    finalized: dict[int, dict[str, object]] = {}
    pending: list[dict[str, object]] = []

    # Pass 1: resolve rows that don't need candidate scoring (missing name, exact
    # match) immediately; queue everything else, reusing cached candidate subsets
    # and fuzzy shortlists for rows that share a district/region/query.
    for position, (record_id, row) in enumerate(records_to_match.iterrows(), start=1):
        submitted_settlement = row.get(settlement_col, "") if settlement_col else ""
        submitted_district = row.get(district_col, "") if district_col else ""
        submitted_region = row.get(region_col, "") if region_col else ""
        source_row = row.get(source_row_col, record_id + 2) if source_row_col else record_id + 2

        if progress_callback:
            progress_callback(position, total, f"Matching {submitted_settlement or 'record'}")

        if not normalize_text(submitted_settlement):
            finalized[position] = _match_candidate_to_row(
                int(record_id),
                source_row,
                submitted_settlement,
                submitted_district,
                submitted_region,
                None,
                prepared,
                "none",
                "Settlement name is missing.",
            )
            continue

        district_norm = normalize_text(submitted_district)
        region_norm = normalize_text(submitted_region)
        subset_key = (district_norm, region_norm)
        candidates = candidate_subset_cache.get(subset_key)
        if candidates is None:
            candidates = _candidate_subset(prepared, submitted_district, submitted_region)
            candidate_subset_cache[subset_key] = candidates

        exact_candidates = candidates[
            candidates["_settlement_norm"] == normalize_text(submitted_settlement)
        ]
        if not exact_candidates.empty:
            candidate = exact_candidates.iloc[0]
            finalized[position] = _match_candidate_to_row(
                int(record_id),
                source_row,
                submitted_settlement,
                submitted_district,
                submitted_region,
                candidate,
                prepared,
                "exact",
                "Exact settlement name match found in gazetteer.",
                use_ollama,
                ollama_cache,
            )
            continue

        query = normalize_text(
            f"{submitted_settlement} {submitted_district} {submitted_region}"
        )
        top_key = (query, district_norm, region_norm)
        top_indices = top_candidate_cache.get(top_key)
        if top_indices is None:
            top_indices = _extract_top_candidates(query, candidates, limit=8)
            top_candidate_cache[top_key] = top_indices

        pending.append(
            {
                "position": position,
                "record_id": int(record_id),
                "source_row": source_row,
                "submitted_settlement": submitted_settlement,
                "submitted_district": submitted_district,
                "submitted_region": submitted_region,
                "candidates": candidates,
                "top_indices": top_indices,
                "query": query,
            }
        )

    # Pass 2: batch-encode every distinct pending query once (instead of once per
    # row) and score it against the already-embedded gazetteer.
    query_embeddings: dict[str, Any] = {}
    if semantic_model is not None and gazetteer_embeddings is not None and pending:
        unique_queries = list({item["query"] for item in pending if item["top_indices"]})
        if unique_queries:
            encoded = semantic_model.encode(unique_queries, normalize_embeddings=True, show_progress_bar=False)
            query_embeddings = dict(zip(unique_queries, encoded, strict=False))

    for item in pending:
        top_indices = item["top_indices"]
        candidates = item["candidates"]
        best_idx = top_indices[0] if top_indices else None
        method = "rapidfuzz"
        semantic_score = 0.0

        query_embedding = query_embeddings.get(item["query"]) if top_indices else None
        if query_embedding is not None:
            candidate_embeddings = gazetteer_embeddings[top_indices]
            scores = np.matmul(candidate_embeddings, query_embedding)
            best_position = int(np.argmax(scores))
            best_idx = top_indices[best_position]
            semantic_score = float(scores[best_position] * 100)
            method = "sentence_transformer"

        candidate = candidates.loc[best_idx] if best_idx is not None else None
        reason_prefix = "Best fuzzy gazetteer candidate selected."
        if method == "sentence_transformer":
            reason_prefix = f"Best semantic candidate selected ({semantic_score:.1f}% embedding similarity)."

        finalized[item["position"]] = _match_candidate_to_row(
            item["record_id"],
            item["source_row"],
            item["submitted_settlement"],
            item["submitted_district"],
            item["submitted_region"],
            candidate,
            prepared,
            method,
            reason_prefix,
            use_ollama,
            ollama_cache,
        )

    matches = [finalized[position] for position in sorted(finalized)]
    return pd.DataFrame(matches, columns=MATCH_COLUMNS)


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
        "auto_accepted": int((status == "auto_accepted").sum()),
        "needs_review": int((status == "needs_review").sum()),
        "unresolved": int((status == "unresolved").sum()),
        "average_confidence": round(float(matches_df["confidence"].fillna(0).mean()), 1),
    }
