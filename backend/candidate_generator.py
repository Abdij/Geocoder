from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backend.text_normalizer import normalize_place_name

try:
    from rapidfuzz import fuzz as _fuzz
    from rapidfuzz import process as _process
except ImportError:  # pragma: no cover - exercised only without rapidfuzz installed.
    _fuzz = None
    _process = None

# Documented combination: WRatio already blends several internal strategies
# so it carries the most weight; token_sort/token_set catch word-order and
# subset differences (e.g. a dropped "IDP Camp" suffix) that plain ratio
# misses; plain ratio keeps a strong signal for near-identical strings.
_FUZZY_METRIC_WEIGHTS = {
    "ratio": 0.20,
    "WRatio": 0.35,
    "token_sort_ratio": 0.20,
    "token_set_ratio": 0.25,
}

DEFAULT_CANDIDATE_LIMIT = 5
_FUZZY_SHORTLIST_SIZE = 8


def fuzzy_name_score(left: str, right: str) -> float:
    """Combine multiple RapidFuzz metrics into one normalized 0-100 name score.

    Falls back to difflib's SequenceMatcher (same fallback the rest of the
    app already uses) when RapidFuzz isn't installed, so matching keeps
    working - just with a coarser signal - rather than failing outright.
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 100.0
    if _fuzz is None:
        from difflib import SequenceMatcher

        return round(SequenceMatcher(None, left, right).ratio() * 100, 1)

    combined = sum(
        getattr(_fuzz, metric)(left, right) * weight for metric, weight in _FUZZY_METRIC_WEIGHTS.items()
    )
    return round(float(combined), 1)


@dataclass
class Candidate:
    gazetteer_id: str
    settlement: str
    district: str
    region: str
    latitude: float | None
    longitude: float | None
    matching_method: str
    name_score: float
    district_score: float
    region_score: float
    semantic_score: float | None = None
    rank: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def _admin_score(submitted: str, candidate: str) -> float:
    """Similarity between a submitted and candidate district/region name.

    100 when both are known and match, 60 when either side is simply
    unknown (neither a match nor a contradiction), and a fuzzy score
    otherwise - mirrors the existing app's treatment of missing admin
    fields as neutral rather than penalized.
    """
    submitted_norm = normalize_place_name(submitted)
    candidate_norm = normalize_place_name(candidate)
    if not submitted_norm or not candidate_norm:
        return 60.0
    if submitted_norm == candidate_norm:
        return 100.0
    return fuzzy_name_score(submitted_norm, candidate_norm)


def _row_to_candidate(row: pd.Series, columns: dict[str, str | None], method: str, name_score: float) -> Candidate:
    settlement_col = columns.get("settlement")
    district_col = columns.get("district")
    region_col = columns.get("region")
    lat_col = columns.get("latitude")
    lon_col = columns.get("longitude")

    submitted_district = row.get("_submitted_district", "")
    submitted_region = row.get("_submitted_region", "")

    candidate_district = row.get(district_col, "") if district_col else ""
    candidate_region = row.get(region_col, "") if region_col else ""

    latitude = row.get(lat_col) if lat_col else None
    longitude = row.get(lon_col) if lon_col else None

    return Candidate(
        gazetteer_id=str(row.get("gazetteer_id", "")),
        settlement=str(row.get(settlement_col, "")) if settlement_col else "",
        district=str(candidate_district) if pd.notna(candidate_district) else "",
        region=str(candidate_region) if pd.notna(candidate_region) else "",
        latitude=float(latitude) if latitude is not None and pd.notna(latitude) else None,
        longitude=float(longitude) if longitude is not None and pd.notna(longitude) else None,
        matching_method=method,
        name_score=name_score,
        district_score=_admin_score(submitted_district, candidate_district),
        region_score=_admin_score(submitted_region, candidate_region),
    )


def _exact_tier(
    prepared: pd.DataFrame,
    settlement_norm: str,
    district_norm: str,
    region_norm: str,
    columns: dict[str, str | None],
    require_district: bool,
    require_region: bool,
) -> pd.DataFrame:
    mask = prepared["_settlement_norm"] == settlement_norm
    if require_district:
        mask &= prepared["_district_norm"] == district_norm
    if require_region:
        mask &= prepared["_region_norm"] == region_norm
    return prepared[mask]


def _unique_national_tier(prepared: pd.DataFrame, settlement_norm: str) -> pd.DataFrame:
    matches = prepared[prepared["_settlement_norm"] == settlement_norm]
    # Only trust a name-only match when it resolves to exactly one gazetteer
    # entry nationally - two settlements sharing a name in different
    # districts must not be silently disambiguated by this tier.
    return matches if len(matches) == 1 else prepared.iloc[0:0]


def _fuzzy_tier(
    prepared: pd.DataFrame,
    query: str,
    limit: int = _FUZZY_SHORTLIST_SIZE,
) -> pd.DataFrame:
    if prepared.empty or not query:
        return prepared.iloc[0:0]
    candidate_texts = prepared["_candidate_text"].fillna("").tolist()
    candidate_index = prepared.index.tolist()

    if _process is not None and _fuzz is not None:
        extracted = _process.extract(query, candidate_texts, scorer=_fuzz.WRatio, limit=limit)
        positions = [item[2] for item in extracted if item[1] > 0]
    else:
        scored = sorted(
            range(len(candidate_texts)),
            key=lambda i: fuzzy_name_score(query, candidate_texts[i]),
            reverse=True,
        )
        positions = [i for i in scored[:limit] if fuzzy_name_score(query, candidate_texts[i]) > 0]

    return prepared.loc[[candidate_index[i] for i in positions]]


def generate_candidates(
    *,
    submitted_settlement: str,
    submitted_district: str,
    submitted_region: str,
    prepared_gazetteer: pd.DataFrame,
    columns: dict[str, str | None],
    alias_lookup=None,
    semantic_model=None,
    gazetteer_embeddings: np.ndarray | None = None,
    top_n: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[Candidate]:
    """Generate up to top_n ranked candidates using the layered search order.

    Order: approved alias -> exact settlement+district+region -> exact
    settlement+district -> exact settlement+region -> unique national exact
    settlement -> district-constrained fuzzy -> region-constrained fuzzy ->
    national fuzzy fallback -> optional semantic re-ranking of the fuzzy
    shortlist. The first tier that produces results is used; later tiers
    only run when an earlier one comes up empty. Does not stop at (and
    immediately accept) the first RapidFuzz hit - always returns the
    ranked shortlist for the reviewer to compare.
    """
    # Response data often submits a facility name ("Kaharey Health Center")
    # rather than the settlement itself; strip that noise before matching
    # against the (already-clean) gazetteer settlement names.
    settlement_norm = normalize_place_name(submitted_settlement, strip_generic_suffixes=True)
    district_norm = normalize_place_name(submitted_district)
    region_norm = normalize_place_name(submitted_region)

    if prepared_gazetteer.empty or not settlement_norm:
        return []

    tagged = prepared_gazetteer.copy()
    tagged["_submitted_district"] = submitted_district
    tagged["_submitted_region"] = submitted_region

    candidates: list[Candidate] = []
    seen_ids: set[str] = set()

    def _add(rows: pd.DataFrame, method: str, name_score_override: float | None = None) -> None:
        for _, row in rows.iterrows():
            gid = str(row.get("gazetteer_id", ""))
            if gid and gid in seen_ids:
                continue
            score = name_score_override if name_score_override is not None else 100.0
            candidate = _row_to_candidate(row, columns, method, score)
            candidates.append(candidate)
            if gid:
                seen_ids.add(gid)

    # 1. Approved alias match - confirmed prior human judgment, always
    # considered first regardless of what the deterministic tiers below find.
    if alias_lookup is not None:
        alias = alias_lookup(settlement_norm, district_norm, region_norm)
        if alias is not None:
            alias_id = str(alias.get("official_gazetteer_id", ""))
            match_rows = tagged[tagged["gazetteer_id"].astype(str) == alias_id]
            if not match_rows.empty:
                _add(match_rows, "approved_alias", name_score_override=100.0)
            else:
                # Alias points at a gazetteer_id no longer present in this
                # upload; fall back to the deterministic tiers below instead
                # of fabricating a candidate with no real gazetteer row.
                pass

    # 2-4. Exact tiers, most specific first.
    exact_tiers = [
        (True, True),
        (True, False),
        (False, True),
    ]
    exact_hit = False
    for require_district, require_region in exact_tiers:
        rows = _exact_tier(tagged, settlement_norm, district_norm, region_norm, columns, require_district, require_region)
        if not rows.empty:
            _add(rows, "exact")
            exact_hit = True
            break

    # 5. Unique national exact settlement match.
    if not exact_hit:
        rows = _unique_national_tier(tagged, settlement_norm)
        if not rows.empty:
            _add(rows, "exact_national_unique")
            exact_hit = True

    # 6-8. Fuzzy tiers: district-constrained, then region-constrained, then national.
    # Built from the already-normalized (and suffix-stripped) parts rather than
    # re-normalizing the raw concatenation, since a trailing suffix like
    # "Health Center" would no longer be at the end of the string once district
    # and region are appended, so it would never get caught by the suffix strip.
    fuzzy_rows = tagged.iloc[0:0]
    query = " ".join(part for part in (settlement_norm, district_norm, region_norm) if part)
    if district_norm:
        district_subset = tagged[tagged["_district_norm"] == district_norm]
        fuzzy_rows = _fuzzy_tier(district_subset, query)
    if fuzzy_rows.empty and region_norm:
        region_subset = tagged[tagged["_region_norm"] == region_norm]
        fuzzy_rows = _fuzzy_tier(region_subset, query)
    if fuzzy_rows.empty:
        fuzzy_rows = _fuzzy_tier(tagged, query)

    # Track (candidate, source_row) together so the semantic re-ranking step
    # below can align scores correctly even when some fuzzy rows are skipped
    # as duplicates of a candidate already added by an earlier tier - zipping
    # candidates against fuzzy_rows by position/count would silently
    # misalign as soon as any row got skipped.
    fuzzy_candidates_with_rows: list[tuple[Candidate, pd.Series]] = []
    if not fuzzy_rows.empty:
        for _, row in fuzzy_rows.iterrows():
            gid = str(row.get("gazetteer_id", ""))
            if gid and gid in seen_ids:
                continue
            settlement_col = columns.get("settlement")
            candidate_text = row.get(settlement_col, "") if settlement_col else ""
            score = fuzzy_name_score(settlement_norm, normalize_place_name(candidate_text))
            candidate = _row_to_candidate(row, columns, "rapidfuzz", score)
            candidates.append(candidate)
            fuzzy_candidates_with_rows.append((candidate, row))
            if gid:
                seen_ids.add(gid)

    # 9. Optional semantic re-ranking of whatever fuzzy candidates were found -
    # re-ranks the shortlist rather than comparing the query against every
    # gazetteer row, matching the app's existing performance-conscious design.
    if semantic_model is not None and gazetteer_embeddings is not None and fuzzy_candidates_with_rows:
        try:
            query_embedding = semantic_model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
            row_positions = [prepared_gazetteer.index.get_loc(row.name) for _, row in fuzzy_candidates_with_rows]
            candidate_embeddings = gazetteer_embeddings[row_positions]
            scores = np.matmul(candidate_embeddings, query_embedding)
            for (candidate, _row), semantic_score in zip(fuzzy_candidates_with_rows, scores, strict=False):
                candidate.semantic_score = round(float(semantic_score) * 100, 1)
                candidate.matching_method = "semantic_rerank"
        except Exception:
            # Semantic re-ranking is optional - a failure here must not break
            # matching, only skip the extra signal for this run.
            pass

    for rank, candidate in enumerate(
        sorted(candidates, key=lambda c: (c.matching_method != "approved_alias", -c.name_score)), start=1
    ):
        candidate.rank = rank

    return candidates[:top_n]
