from __future__ import annotations

import pandas as pd

from backend.candidate_generator import fuzzy_name_score, generate_candidates
from backend.text_normalizer import normalize_place_name

COLUMNS = {
    "settlement": "Settlement",
    "district": "District",
    "region": "Region",
    "latitude": "Latitude",
    "longitude": "Longitude",
}


def _prepared(rows: list[dict]) -> pd.DataFrame:
    columns = ["Settlement", "District", "Region", "Latitude", "Longitude"]
    df = pd.DataFrame(rows, columns=columns)
    df["gazetteer_id"] = [f"gaz_{i}" for i in range(len(df))]
    df["_settlement_norm"] = df["Settlement"].map(normalize_place_name)
    df["_district_norm"] = df["District"].map(normalize_place_name)
    df["_region_norm"] = df["Region"].map(normalize_place_name)
    df["_candidate_text"] = (df["Settlement"] + " " + df["District"] + " " + df["Region"]).map(normalize_place_name)
    return df


# --- fuzzy_name_score -----------------------------------------------------


def test_fuzzy_name_score_identical_strings_is_100():
    assert fuzzy_name_score("baidoa", "baidoa") == 100.0


def test_fuzzy_name_score_empty_strings_is_zero():
    assert fuzzy_name_score("", "baidoa") == 0.0
    assert fuzzy_name_score("baidoa", "") == 0.0


def test_fuzzy_name_score_known_transliteration_pairs_score_higher_than_unrelated():
    pairs = [
        ("baydhabo", "baidoa"),
        ("mogadisho", "muqdisho"),
        ("muqdishu", "muqdisho"),
        ("johwar", "jowhar"),
        ("beledweyne", "belet weyne"),
        ("xudur", "hudur"),
    ]
    unrelated_score = fuzzy_name_score("baidoa", "garowe")
    for left, right in pairs:
        score = fuzzy_name_score(left, right)
        assert score > unrelated_score, f"{left} vs {right} scored {score}, not higher than unrelated {unrelated_score}"


# --- generate_candidates: exact tiers --------------------------------------


def test_exact_settlement_district_region_match():
    prepared = _prepared(
        [
            {"Settlement": "Baidoa", "District": "Baidoa", "Region": "Bay", "Latitude": 3.1167, "Longitude": 43.65},
            {"Settlement": "Baidoa", "District": "Garowe", "Region": "Nugaal", "Latitude": 8.4, "Longitude": 48.4},
        ]
    )
    results = generate_candidates(
        submitted_settlement="Baidoa",
        submitted_district="Baidoa",
        submitted_region="Bay",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
    )
    assert len(results) == 1
    assert results[0].matching_method == "exact"
    assert results[0].district == "Baidoa"
    assert results[0].name_score == 100.0


def test_exact_settlement_district_falls_back_when_region_mismatched():
    prepared = _prepared(
        [{"Settlement": "Baidoa", "District": "Baidoa", "Region": "Bay", "Latitude": 3.1167, "Longitude": 43.65}]
    )
    results = generate_candidates(
        submitted_settlement="Baidoa",
        submitted_district="Baidoa",
        submitted_region="WrongRegion",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
    )
    assert len(results) == 1
    assert results[0].matching_method == "exact"


def test_unique_national_exact_match_when_no_district_or_region_given():
    prepared = _prepared(
        [
            {"Settlement": "Baidoa", "District": "Baidoa", "Region": "Bay", "Latitude": 3.1167, "Longitude": 43.65},
            {"Settlement": "Garowe", "District": "Garowe", "Region": "Nugaal", "Latitude": 8.4, "Longitude": 48.4},
        ]
    )
    results = generate_candidates(
        submitted_settlement="Baidoa",
        submitted_district="",
        submitted_region="",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
    )
    assert len(results) >= 1
    assert results[0].matching_method == "exact_national_unique"
    assert results[0].settlement == "Baidoa"


def test_ambiguous_national_name_does_not_use_unique_tier():
    # "Kaharey" exists in two different districts with no submitted district
    # to disambiguate - the unique-national tier must not silently guess.
    prepared = _prepared(
        [
            {"Settlement": "Kaharey", "District": "Doolow", "Region": "Gedo", "Latitude": 4.14, "Longitude": 42.19},
            {"Settlement": "Kaharey", "District": "Luuq", "Region": "Gedo", "Latitude": 3.94, "Longitude": 42.44},
        ]
    )
    results = generate_candidates(
        submitted_settlement="Kaharey",
        submitted_district="",
        submitted_region="",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
    )
    assert all(r.matching_method != "exact_national_unique" for r in results)


# --- generate_candidates: fuzzy tiers ---------------------------------------


def test_district_constrained_fuzzy_match():
    prepared = _prepared(
        [
            {"Settlement": "Deeyniile", "District": "Mogadishu", "Region": "Banadir", "Latitude": 2.09, "Longitude": 45.27},
            {"Settlement": "Deeyniile", "District": "Baidoa", "Region": "Bay", "Latitude": 3.11, "Longitude": 43.65},
        ]
    )
    results = generate_candidates(
        submitted_settlement="Deynile",
        submitted_district="Mogadishu",
        submitted_region="Banadir",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
    )
    assert len(results) >= 1
    assert results[0].district == "Mogadishu"
    assert results[0].matching_method in {"rapidfuzz", "semantic_rerank"}


def test_national_fuzzy_fallback_when_no_district_or_region_candidates():
    prepared = _prepared(
        [{"Settlement": "Jowhar", "District": "Jowhar", "Region": "Middle Shabelle", "Latitude": 2.78, "Longitude": 45.5}]
    )
    results = generate_candidates(
        submitted_settlement="Johwar",
        submitted_district="SomeOtherDistrict",
        submitted_region="SomeOtherRegion",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
    )
    assert len(results) >= 1
    assert results[0].settlement == "Jowhar"


def test_does_not_stop_at_first_fuzzy_hit_returns_multiple_candidates():
    prepared = _prepared(
        [
            {"Settlement": "Baidoa", "District": "Baidoa", "Region": "Bay", "Latitude": 3.1167, "Longitude": 43.65},
            {"Settlement": "Baydhabo", "District": "Baidoa", "Region": "Bay", "Latitude": 3.12, "Longitude": 43.66},
            {"Settlement": "Baydhaba", "District": "Baidoa", "Region": "Bay", "Latitude": 3.13, "Longitude": 43.67},
        ]
    )
    results = generate_candidates(
        submitted_settlement="Baydhabo",
        submitted_district="Baidoa",
        submitted_region="Bay",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
        top_n=5,
    )
    assert len(results) > 1


def test_top_n_limits_returned_candidates():
    rows = [
        {"Settlement": f"Place{i}", "District": "Baidoa", "Region": "Bay", "Latitude": 3.1 + i * 0.01, "Longitude": 43.6}
        for i in range(10)
    ]
    prepared = _prepared(rows)
    results = generate_candidates(
        submitted_settlement="Place0",
        submitted_district="Baidoa",
        submitted_region="Bay",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
        top_n=3,
    )
    assert len(results) <= 3


# --- generate_candidates: alias override -----------------------------------


def test_approved_alias_takes_priority_over_exact_match():
    prepared = _prepared(
        [
            {"Settlement": "Kaharey", "District": "Doolow", "Region": "Gedo", "Latitude": 4.14, "Longitude": 42.19},
            {"Settlement": "Kaharey", "District": "Luuq", "Region": "Gedo", "Latitude": 3.94, "Longitude": 42.44},
        ]
    )
    # Analysts previously confirmed the Luuq gazetteer_id (gaz_1) is correct
    # for this submitted context, even though an exact-tier match would
    # otherwise be ambiguous between the two rows.
    alias_gid = prepared.iloc[1]["gazetteer_id"]

    def alias_lookup(name_norm, district_norm, region_norm):
        return {"official_gazetteer_id": alias_gid}

    results = generate_candidates(
        submitted_settlement="Kaharey",
        submitted_district="",
        submitted_region="",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
        alias_lookup=alias_lookup,
    )
    assert results[0].matching_method == "approved_alias"
    assert results[0].gazetteer_id == alias_gid
    assert results[0].rank == 1


def test_alias_lookup_returning_none_falls_back_to_deterministic_tiers():
    prepared = _prepared(
        [{"Settlement": "Baidoa", "District": "Baidoa", "Region": "Bay", "Latitude": 3.1167, "Longitude": 43.65}]
    )
    results = generate_candidates(
        submitted_settlement="Baidoa",
        submitted_district="Baidoa",
        submitted_region="Bay",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
        alias_lookup=lambda *args: None,
    )
    assert results[0].matching_method == "exact"


# --- edge cases --------------------------------------------------------------


def test_empty_gazetteer_returns_no_candidates():
    prepared = _prepared([])
    results = generate_candidates(
        submitted_settlement="Baidoa",
        submitted_district="Baidoa",
        submitted_region="Bay",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
    )
    assert results == []


def test_empty_submitted_settlement_returns_no_candidates():
    prepared = _prepared(
        [{"Settlement": "Baidoa", "District": "Baidoa", "Region": "Bay", "Latitude": 3.1167, "Longitude": 43.65}]
    )
    results = generate_candidates(
        submitted_settlement="",
        submitted_district="Baidoa",
        submitted_region="Bay",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
    )
    assert results == []


# --- generate_candidates: semantic re-ranking / fallback --------------------


class _FakeSemanticModel:
    """Deterministic fake embedding model - avoids downloading a real one in tests."""

    def __init__(self, embedding_by_text: dict[str, list[float]], should_raise: bool = False):
        self._embeddings = embedding_by_text
        self._should_raise = should_raise

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        if self._should_raise:
            raise RuntimeError("simulated model failure")
        import numpy as np

        return np.array([self._embeddings.get(text, [0.0, 0.0]) for text in texts])


def test_semantic_model_populates_semantic_score_for_fuzzy_candidates():
    prepared = _prepared(
        [
            {"Settlement": "Deeyniile", "District": "Mogadishu", "Region": "Banadir", "Latitude": 2.09, "Longitude": 45.27},
        ]
    )
    query = normalize_place_name("Deynile Mogadishu Banadir")
    candidate_text = prepared.iloc[0]["_candidate_text"]
    fake_model = _FakeSemanticModel({query: [1.0, 0.0], candidate_text: [1.0, 0.0]})
    embeddings = fake_model.encode([candidate_text])

    results = generate_candidates(
        submitted_settlement="Deynile",
        submitted_district="Mogadishu",
        submitted_region="Banadir",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
        semantic_model=fake_model,
        gazetteer_embeddings=embeddings,
    )
    assert len(results) >= 1
    reranked = [c for c in results if c.matching_method == "semantic_rerank"]
    assert reranked, "expected at least one candidate to be semantically re-ranked"
    assert reranked[0].semantic_score == 100.0  # identical embedding vectors -> cosine similarity 1.0


def test_semantic_model_failure_falls_back_to_fuzzy_without_crashing():
    prepared = _prepared(
        [{"Settlement": "Deeyniile", "District": "Mogadishu", "Region": "Banadir", "Latitude": 2.09, "Longitude": 45.27}]
    )
    candidate_text = prepared.iloc[0]["_candidate_text"]
    failing_model = _FakeSemanticModel({}, should_raise=True)
    embeddings = [[1.0, 0.0]]  # any placeholder; encode() will raise before using it

    results = generate_candidates(
        submitted_settlement="Deynile",
        submitted_district="Mogadishu",
        submitted_region="Banadir",
        prepared_gazetteer=prepared,
        columns=COLUMNS,
        semantic_model=failing_model,
        gazetteer_embeddings=embeddings,
    )
    # Matching still succeeds via the fuzzy tier; no semantic_score was assigned.
    assert len(results) >= 1
    assert all(c.matching_method != "semantic_rerank" for c in results)
    assert all(c.semantic_score is None for c in results)
