from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pandas as pd
import pytest

from backend.alias_repository import get_connection
from backend.settlement_matcher import match_records, matching_statistics


@pytest.fixture()
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _response_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Settlement": ["Baydhabo", "Xudur", ""],
            "District": ["Baidoa", "Hudur", "Nowhere"],
            "Region": ["Bay", "Bakool", "Nowhere"],
            "Latitude": [None, None, None],
            "Longitude": [None, None, None],
        }
    )


def _gazetteer_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Settlement": ["Baidoa", "Hudur", "Garowe"],
            "District": ["Baidoa", "Hudur", "Garowe"],
            "Region": ["Bay", "Bakool", "Nugaal"],
            "Latitude": [3.1167, 4.1213, 8.4054],
            "Longitude": [43.65, 43.899, 48.4845],
        }
    )


def _match(db_path: str):
    with patch("backend.settlement_matcher.get_connection", side_effect=lambda: get_connection(db_path)):
        return match_records(_response_df(), _gazetteer_df())


def test_match_records_returns_tuple_of_dataframe_and_candidate_dict(db_path):
    matches_df, candidates_by_record = _match(db_path)
    assert isinstance(matches_df, pd.DataFrame)
    assert isinstance(candidates_by_record, dict)


def test_matching_statistics_still_works_with_the_returned_dataframe(db_path):
    # Baydhabo/Xudur are hard transliteration pairs that fuzzy-only matching
    # (no semantic model enabled here) correctly can't confidently resolve
    # above the stricter 85% needs-review bar - matching_statistics() should
    # still run cleanly over whatever mix of statuses results.
    matches_df, _ = _match(db_path)
    stats = matching_statistics(matches_df)
    assert stats["matched"] + stats["unresolved"] == len(matches_df)
    assert stats["average_confidence"] > 0


def test_candidates_by_record_has_entry_for_each_matched_record(db_path):
    matches_df, candidates_by_record = _match(db_path)
    matched_ids = matches_df.loc[matches_df["suggested_settlement"] != "", "record_id"].tolist()
    for record_id in matched_ids:
        assert record_id in candidates_by_record
        assert len(candidates_by_record[record_id]) >= 1


def test_top_candidate_matches_the_winning_row_in_matches_df(db_path):
    matches_df, candidates_by_record = _match(db_path)
    row = matches_df.loc[matches_df["submitted_settlement"] == "Baydhabo"].iloc[0]
    top_candidate = candidates_by_record[int(row["record_id"])][0]
    assert top_candidate["gazetteer_id"] == row["suggested_gazetteer_id"]
    assert top_candidate["settlement"] == row["suggested_settlement"]
    assert top_candidate["rank"] == 1


def test_candidates_are_ranked_by_descending_confidence(db_path):
    _, candidates_by_record = _match(db_path)
    for candidates in candidates_by_record.values():
        confidences = [c["overall_confidence"] for c in candidates]
        assert confidences == sorted(confidences, reverse=True)
        assert [c["rank"] for c in candidates] == list(range(1, len(candidates) + 1))


def test_record_with_missing_settlement_name_has_no_candidates(db_path):
    matches_df, candidates_by_record = _match(db_path)
    empty_row = matches_df.loc[matches_df["submitted_district"] == "Nowhere"].iloc[0]
    assert int(empty_row["record_id"]) not in candidates_by_record
    assert empty_row["status"] == "unresolved"
