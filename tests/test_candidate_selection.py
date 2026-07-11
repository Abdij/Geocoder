from __future__ import annotations

import pandas as pd

from frontend.dashboard_page import apply_candidate_selection

CHOSEN_CANDIDATE = {
    "rank": 2,
    "gazetteer_id": "gaz_alt456",
    "settlement": "Kaharey Alt",
    "district": "Luuq",
    "region": "Gedo",
    "latitude": 3.94,
    "longitude": 42.44,
    "overall_confidence": 88.0,
}


def _matches_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_id": 5,
                "submitted_settlement": "Kaharey",
                "suggested_settlement": "Kaharey Original",
                "suggested_district": "Doolow",
                "suggested_region": "Gedo",
                "suggested_gazetteer_id": "gaz_orig123",
                "latitude": 4.14,
                "longitude": 42.19,
                "official_district": "Doolow",
                "official_region": "Gedo",
                "official_latitude": 4.14,
                "official_longitude": 42.19,
                "confidence": 71.4,
                "overall_confidence": 71.4,
                "matching_method": "rapidfuzz",
                "candidate_rank": 1,
                "status": "needs_review",
                "decision_status": "needs_review",
                "accept": False,
                "reject": False,
            }
        ]
    )


def test_apply_candidate_selection_overwrites_suggested_fields():
    result = apply_candidate_selection(_matches_df(), record_id=5, chosen_candidate=CHOSEN_CANDIDATE)
    row = result.iloc[0]
    assert row["suggested_settlement"] == "Kaharey Alt"
    assert row["suggested_district"] == "Luuq"
    assert row["suggested_gazetteer_id"] == "gaz_alt456"
    assert row["latitude"] == 3.94
    assert row["longitude"] == 42.44
    assert row["official_latitude"] == 3.94


def test_apply_candidate_selection_marks_accepted_with_manual_method():
    result = apply_candidate_selection(_matches_df(), record_id=5, chosen_candidate=CHOSEN_CANDIDATE)
    row = result.iloc[0]
    assert bool(row["accept"]) is True
    assert bool(row["reject"]) is False
    assert row["status"] == "accepted"
    assert row["decision_status"] == "accepted"
    assert row["matching_method"] == "manual_selection"


def test_apply_candidate_selection_updates_confidence_to_chosen_candidates_score():
    result = apply_candidate_selection(_matches_df(), record_id=5, chosen_candidate=CHOSEN_CANDIDATE)
    row = result.iloc[0]
    assert row["confidence"] == 88.0
    assert row["overall_confidence"] == 88.0
    assert row["candidate_rank"] == 2


def test_apply_candidate_selection_does_not_mutate_other_rows():
    df = pd.concat([_matches_df(), _matches_df().assign(record_id=6)], ignore_index=True)
    result = apply_candidate_selection(df, record_id=5, chosen_candidate=CHOSEN_CANDIDATE)
    untouched_row = result.loc[result["record_id"] == 6].iloc[0]
    assert untouched_row["suggested_settlement"] == "Kaharey Original"
    assert untouched_row["status"] == "needs_review"


def test_apply_candidate_selection_returns_a_copy_not_the_original():
    original = _matches_df()
    result = apply_candidate_selection(original, record_id=5, chosen_candidate=CHOSEN_CANDIDATE)
    assert original.iloc[0]["suggested_settlement"] == "Kaharey Original"
    assert result.iloc[0]["suggested_settlement"] == "Kaharey Alt"
