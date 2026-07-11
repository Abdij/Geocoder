from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pandas as pd
import pytest

from backend.alias_repository import get_connection, list_approved_aliases
from backend.geocoder import apply_geocodes
from backend.review_repository import list_rejected_candidates, list_review_decisions


@pytest.fixture()
def db_path():
    # apply_geocodes() opens and closes its own connection per call (the
    # same lifecycle match_records() uses in real usage), so tests use a
    # temp file-backed database and re-open a fresh connection afterward
    # to inspect state, rather than fighting sqlite3.Connection's
    # unpatchable close() method.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # get_connection() creates it fresh
    yield path
    if os.path.exists(path):
        os.remove(path)


def _response_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Settlement": ["Kaharey", "Deynile"],
            "District": ["Doolow", "Mogadishu"],
            "Region": ["Gedo", "Banadir"],
        }
    )


def _match_row(**overrides) -> dict:
    base = {
        "record_id": 0,
        "run_id": "run-1",
        "submitted_settlement": "Kaharey",
        "submitted_district": "Doolow",
        "submitted_region": "Gedo",
        "normalized_submitted_settlement": "kaharey",
        "suggested_settlement": "Kaharey",
        "suggested_district": "Doolow",
        "suggested_region": "Gedo",
        "suggested_gazetteer_id": "gaz_abc123",
        "latitude": 4.14,
        "longitude": 42.19,
        "confidence": 96.0,
        "matching_method": "exact",
        "status": "auto_accepted",
        "accept": True,
        "reject": False,
    }
    base.update(overrides)
    return base


def _run(db_path: str, matches_df: pd.DataFrame) -> None:
    with patch("backend.geocoder.get_connection", side_effect=lambda: get_connection(db_path)):
        apply_geocodes(_response_df(), matches_df)


def test_accepted_match_creates_approved_alias(db_path):
    _run(db_path, pd.DataFrame([_match_row()]))
    conn = get_connection(db_path)
    aliases = list_approved_aliases(conn)
    conn.close()
    assert len(aliases) == 1
    assert aliases.iloc[0]["official_gazetteer_id"] == "gaz_abc123"
    assert aliases.iloc[0]["approval_count"] == 1


def test_accepted_match_records_review_decision(db_path):
    _run(db_path, pd.DataFrame([_match_row()]))
    conn = get_connection(db_path)
    decisions = list_review_decisions(conn)
    conn.close()
    assert len(decisions) == 1
    assert decisions.iloc[0]["decision"] == "accepted"
    assert decisions.iloc[0]["final_gazetteer_id"] == "gaz_abc123"


def test_rejected_match_records_rejection_not_alias(db_path):
    _run(
        db_path,
        pd.DataFrame(
            [_match_row(record_id=1, accept=False, reject=True, status="rejected", submitted_settlement="Deynile")]
        ),
    )
    conn = get_connection(db_path)
    aliases = list_approved_aliases(conn)
    rejections = list_rejected_candidates(conn)
    conn.close()
    assert len(aliases) == 0
    assert len(rejections) == 1
    assert rejections.iloc[0]["rejected_gazetteer_id"] == "gaz_abc123"


def test_untouched_match_records_nothing(db_path):
    _run(db_path, pd.DataFrame([_match_row(accept=False, reject=False, status="needs_review")]))
    conn = get_connection(db_path)
    aliases_empty = list_approved_aliases(conn).empty
    decisions_empty = list_review_decisions(conn).empty
    conn.close()
    assert aliases_empty
    assert decisions_empty


def test_resaving_same_decision_does_not_duplicate_or_inflate_approval_count(db_path):
    matches_df = pd.DataFrame([_match_row()])
    _run(db_path, matches_df)
    # Analyst clicks "Save Reviewed Matches" again without changing anything.
    _run(db_path, matches_df)

    conn = get_connection(db_path)
    aliases = list_approved_aliases(conn)
    decisions = list_review_decisions(conn)
    conn.close()
    assert len(aliases) == 1
    assert aliases.iloc[0]["approval_count"] == 1
    assert len(decisions) == 1


def test_empty_matches_df_does_not_error(db_path):
    _run(db_path, pd.DataFrame())
    conn = get_connection(db_path)
    aliases_empty = list_approved_aliases(conn).empty
    conn.close()
    assert aliases_empty
