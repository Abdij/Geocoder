from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.utils import output_path

AUDIT_COLUMNS = [
    "run_id",
    "export_timestamp",
    "record_id",
    "submitted_settlement",
    "normalized_submitted_settlement",
    "suggested_settlement",
    "suggested_gazetteer_id",
    "name_score",
    "district_score",
    "region_score",
    "semantic_score",
    "spatial_score",
    "historical_score",
    "rejection_penalty",
    "overall_confidence",
    "matching_method",
    "model_semantic_used",
    "model_ollama_used",
    "automatic_decision",
    "human_decision",
    "reviewer",
    "reviewed_at",
    "reviewer_note",
]


def build_audit_dataframe(
    matches_df: pd.DataFrame | None,
    review_decisions_df: pd.DataFrame | None = None,
    semantic_used: bool = False,
    ollama_used: bool = False,
) -> pd.DataFrame:
    """Combine automated match results with human review history into one audit table.

    Every score component the pipeline computed, plus whichever review
    decision (if any) an analyst has since recorded for that record, are
    brought together so the export explains both what the automated engine
    decided and what a human ultimately did with it.
    """
    if matches_df is None or matches_df.empty:
        return pd.DataFrame(columns=AUDIT_COLUMNS)

    audit = matches_df.copy()
    audit["model_semantic_used"] = semantic_used
    audit["model_ollama_used"] = ollama_used
    audit["automatic_decision"] = audit.get("status")
    audit["export_timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    llm_note = audit.get("llm_note")

    has_review_history = (
        review_decisions_df is not None and not review_decisions_df.empty and "record_id" in review_decisions_df.columns
    )
    if has_review_history:
        latest_decisions = (
            review_decisions_df.sort_values("reviewed_at")
            .groupby("record_id", as_index=False)
            .last()[["record_id", "decision", "reviewer", "reviewed_at", "reviewer_note"]]
            .rename(columns={"decision": "human_decision"})
        )
        audit = audit.merge(latest_decisions, on="record_id", how="left")
        # Prefer the analyst's own note over the LLM's advisory note once a
        # human has actually reviewed the record.
        if llm_note is not None:
            audit["reviewer_note"] = audit["reviewer_note"].where(audit["reviewer_note"].notna(), llm_note)
    else:
        audit["human_decision"] = None
        audit["reviewer"] = None
        audit["reviewed_at"] = None
        audit["reviewer_note"] = llm_note

    available_columns = [column for column in AUDIT_COLUMNS if column in audit.columns]
    return audit[available_columns]


def export_audit_csv(
    matches_df: pd.DataFrame | None,
    review_decisions_df: pd.DataFrame | None = None,
    semantic_used: bool = False,
    ollama_used: bool = False,
) -> Path:
    audit_df = build_audit_dataframe(matches_df, review_decisions_df, semantic_used, ollama_used)
    path = output_path("audit_log.csv")
    audit_df.to_csv(path, index=False)
    return path


def export_audit_excel(
    matches_df: pd.DataFrame | None,
    review_decisions_df: pd.DataFrame | None = None,
    semantic_used: bool = False,
    ollama_used: bool = False,
) -> Path:
    audit_df = build_audit_dataframe(matches_df, review_decisions_df, semantic_used, ollama_used)
    path = output_path("audit_log.xlsx")
    audit_df.to_excel(path, index=False, engine="xlsxwriter")
    return path
