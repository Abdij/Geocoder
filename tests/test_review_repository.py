from __future__ import annotations

import pytest

from backend.alias_repository import get_connection
from backend.review_repository import (
    get_rejection_count,
    has_existing_decision,
    list_rejected_candidates,
    list_review_decisions,
    record_rejected_candidate,
    record_review_decision,
)


@pytest.fixture()
def conn():
    connection = get_connection(":memory:")
    yield connection
    connection.close()


def test_record_review_decision_inserts_a_row(conn):
    decision_id = record_review_decision(
        conn,
        record_id=1,
        run_id="run-2026-07-11",
        submitted_name="Kaharey",
        submitted_district="Doolow",
        submitted_region="Gedo",
        suggested_gazetteer_id="gaz_abc123",
        final_gazetteer_id="gaz_abc123",
        decision="accepted",
        confidence=93.8,
        matching_method="rapidfuzz",
        reviewer="analyst1",
        reviewer_note="Confirmed spelling variant.",
    )
    decisions = list_review_decisions(conn)
    assert len(decisions) == 1
    assert decisions.iloc[0]["decision_id"] == decision_id
    assert decisions.iloc[0]["decision"] == "accepted"


def test_repeated_review_of_same_record_preserves_history(conn):
    record_review_decision(
        conn,
        record_id=1,
        run_id="run-1",
        submitted_name="Kaharey",
        submitted_district="Doolow",
        submitted_region="Gedo",
        suggested_gazetteer_id="gaz_abc123",
        final_gazetteer_id=None,
        decision="needs_review",
        confidence=80.0,
        matching_method="rapidfuzz",
    )
    record_review_decision(
        conn,
        record_id=1,
        run_id="run-1",
        submitted_name="Kaharey",
        submitted_district="Doolow",
        submitted_region="Gedo",
        suggested_gazetteer_id="gaz_abc123",
        final_gazetteer_id="gaz_abc123",
        decision="accepted",
        confidence=80.0,
        matching_method="rapidfuzz",
        reviewer="analyst1",
    )
    decisions = list_review_decisions(conn)
    # Both the original suggestion and the analyst's final call are preserved.
    assert len(decisions) == 2


def test_rejected_candidate_first_rejection_count_is_one(conn):
    record_rejected_candidate(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        rejected_gazetteer_id="gaz_wrong",
        reviewer="analyst1",
        reason="Wrong district",
    )
    count = get_rejection_count(conn, "kaharey", "doolow", "gedo", "gaz_wrong")
    assert count == 1


def test_repeated_rejection_increments_count_instead_of_duplicating(conn):
    for _ in range(3):
        record_rejected_candidate(
            conn,
            normalized_submitted_name="kaharey",
            submitted_district="doolow",
            submitted_region="gedo",
            rejected_gazetteer_id="gaz_wrong",
        )
    count = get_rejection_count(conn, "kaharey", "doolow", "gedo", "gaz_wrong")
    assert count == 3
    assert len(list_rejected_candidates(conn)) == 1


def test_get_rejection_count_is_zero_for_unknown_context(conn):
    assert get_rejection_count(conn, "never-rejected", "district", "region", "gaz_x") == 0


def test_rejection_does_not_affect_a_different_candidate(conn):
    record_rejected_candidate(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        rejected_gazetteer_id="gaz_wrong",
    )
    assert get_rejection_count(conn, "kaharey", "doolow", "gedo", "gaz_correct") == 0


def test_has_existing_decision_false_before_any_decision_recorded(conn):
    assert has_existing_decision(conn, record_id=1, run_id="run-1", decision="accepted") is False


def test_has_existing_decision_true_after_recording(conn):
    record_review_decision(
        conn,
        record_id=1,
        run_id="run-1",
        submitted_name="Kaharey",
        submitted_district="Doolow",
        submitted_region="Gedo",
        suggested_gazetteer_id="gaz_abc123",
        final_gazetteer_id="gaz_abc123",
        decision="accepted",
        confidence=95.0,
        matching_method="exact",
    )
    assert has_existing_decision(conn, record_id=1, run_id="run-1", decision="accepted") is True


def test_has_existing_decision_false_for_a_different_run(conn):
    record_review_decision(
        conn,
        record_id=1,
        run_id="run-1",
        submitted_name="Kaharey",
        submitted_district="Doolow",
        submitted_region="Gedo",
        suggested_gazetteer_id="gaz_abc123",
        final_gazetteer_id="gaz_abc123",
        decision="accepted",
        confidence=95.0,
        matching_method="exact",
    )
    assert has_existing_decision(conn, record_id=1, run_id="run-2", decision="accepted") is False


def test_has_existing_decision_false_without_record_or_run_id(conn):
    assert has_existing_decision(conn, record_id=None, run_id="run-1", decision="accepted") is False
    assert has_existing_decision(conn, record_id=1, run_id=None, decision="accepted") is False
