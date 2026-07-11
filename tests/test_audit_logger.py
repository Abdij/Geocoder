from __future__ import annotations

import pandas as pd

from backend.audit_logger import build_audit_dataframe


def _matches_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_id": 1,
                "run_id": "run-1",
                "submitted_settlement": "Kaharey",
                "normalized_submitted_settlement": "kaharey",
                "suggested_settlement": "Kaharey",
                "suggested_gazetteer_id": "gaz_abc123",
                "name_score": 100.0,
                "district_score": 100.0,
                "region_score": 100.0,
                "semantic_score": None,
                "spatial_score": None,
                "historical_score": None,
                "rejection_penalty": 0.0,
                "overall_confidence": 96.0,
                "matching_method": "exact",
                "status": "auto_accepted",
                "llm_note": None,
            },
            {
                "record_id": 2,
                "run_id": "run-1",
                "submitted_settlement": "Deynile",
                "normalized_submitted_settlement": "deynile",
                "suggested_settlement": "Deeyniile",
                "suggested_gazetteer_id": "gaz_def456",
                "name_score": 87.5,
                "district_score": 100.0,
                "region_score": 100.0,
                "semantic_score": None,
                "spatial_score": None,
                "historical_score": None,
                "rejection_penalty": 0.0,
                "overall_confidence": 93.3,
                "matching_method": "rapidfuzz",
                "status": "needs_review",
                "llm_note": "Candidate 1 is the closest spelling match.",
            },
        ]
    )


def _review_decisions_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "decision_id": 1,
                "record_id": 2,
                "run_id": "run-1",
                "decision": "accepted",
                "reviewer": "analyst1",
                "reviewed_at": "2026-07-11T10:00:00+00:00",
                "reviewer_note": "Confirmed with field team.",
            }
        ]
    )


def test_build_audit_dataframe_empty_matches_returns_empty_with_columns():
    audit_df = build_audit_dataframe(None)
    assert audit_df.empty
    assert "record_id" in audit_df.columns


def test_build_audit_dataframe_includes_all_score_components():
    audit_df = build_audit_dataframe(_matches_df())
    for column in ["name_score", "district_score", "region_score", "overall_confidence"]:
        assert column in audit_df.columns


def test_build_audit_dataframe_records_model_availability():
    audit_df = build_audit_dataframe(_matches_df(), semantic_used=True, ollama_used=False)
    assert audit_df["model_semantic_used"].all()
    assert not audit_df["model_ollama_used"].any()


def test_build_audit_dataframe_without_review_history_has_no_human_decision():
    audit_df = build_audit_dataframe(_matches_df())
    assert audit_df["human_decision"].isna().all()
    # The LLM's advisory note still shows up when no human has reviewed yet.
    row = audit_df.loc[audit_df["record_id"] == 2].iloc[0]
    assert row["reviewer_note"] == "Candidate 1 is the closest spelling match."


def test_build_audit_dataframe_merges_human_decision_when_available():
    audit_df = build_audit_dataframe(_matches_df(), review_decisions_df=_review_decisions_df())
    reviewed_row = audit_df.loc[audit_df["record_id"] == 2].iloc[0]
    assert reviewed_row["human_decision"] == "accepted"
    assert reviewed_row["reviewer"] == "analyst1"
    # The analyst's own note takes priority over the LLM's advisory note.
    assert reviewed_row["reviewer_note"] == "Confirmed with field team."

    untouched_row = audit_df.loc[audit_df["record_id"] == 1].iloc[0]
    assert pd.isna(untouched_row["human_decision"])


def test_build_audit_dataframe_automatic_decision_matches_status():
    audit_df = build_audit_dataframe(_matches_df())
    row = audit_df.loc[audit_df["record_id"] == 1].iloc[0]
    assert row["automatic_decision"] == "auto_accepted"
