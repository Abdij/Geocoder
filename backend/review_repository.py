from __future__ import annotations

import sqlite3

import pandas as pd

from backend.alias_repository import utcnow


def record_review_decision(
    conn: sqlite3.Connection,
    *,
    record_id: int | None,
    run_id: str | None,
    submitted_name: str | None,
    submitted_district: str | None,
    submitted_region: str | None,
    suggested_gazetteer_id: str | None,
    final_gazetteer_id: str | None,
    decision: str,
    confidence: float | None,
    matching_method: str | None,
    reviewer: str | None = None,
    reviewer_note: str | None = None,
) -> int:
    """Append an immutable audit record of an analyst's decision on a match.

    Prior decisions are never overwritten - each call inserts a new row, so
    the full decision history for a record is preserved even if it is
    reviewed more than once.
    """
    cursor = conn.execute(
        """
        INSERT INTO review_decisions (
            record_id, run_id, submitted_name, submitted_district, submitted_region,
            suggested_gazetteer_id, final_gazetteer_id, decision, confidence, matching_method,
            reviewer, reviewed_at, reviewer_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record_id,
            run_id,
            submitted_name,
            submitted_district,
            submitted_region,
            suggested_gazetteer_id,
            final_gazetteer_id,
            decision,
            confidence,
            matching_method,
            reviewer,
            utcnow(),
            reviewer_note,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def record_rejected_candidate(
    conn: sqlite3.Connection,
    *,
    normalized_submitted_name: str,
    submitted_district: str | None,
    submitted_region: str | None,
    rejected_gazetteer_id: str,
    reviewer: str | None = None,
    reason: str | None = None,
) -> int:
    """Record that a candidate was rejected for a given submitted-name context.

    Repeating the same rejection increments rejection_count instead of
    inserting a duplicate row; the official gazetteer record itself is never
    touched or removed, only this rejection note.
    """
    submitted_district = submitted_district or ""
    submitted_region = submitted_region or ""
    now = utcnow()

    existing = conn.execute(
        """
        SELECT rejection_id, rejection_count FROM rejected_candidates
        WHERE normalized_submitted_name = ? AND submitted_district = ? AND submitted_region = ?
          AND rejected_gazetteer_id = ?
        """,
        (normalized_submitted_name, submitted_district, submitted_region, rejected_gazetteer_id),
    ).fetchone()

    if existing is not None:
        conn.execute(
            """
            UPDATE rejected_candidates
            SET rejection_count = ?, last_rejected_at = ?,
                reviewer = COALESCE(?, reviewer), reason = COALESCE(?, reason)
            WHERE rejection_id = ?
            """,
            (existing["rejection_count"] + 1, now, reviewer, reason, existing["rejection_id"]),
        )
        conn.commit()
        return int(existing["rejection_id"])

    cursor = conn.execute(
        """
        INSERT INTO rejected_candidates (
            normalized_submitted_name, submitted_district, submitted_region,
            rejected_gazetteer_id, rejection_count, last_rejected_at, reviewer, reason
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (normalized_submitted_name, submitted_district, submitted_region, rejected_gazetteer_id, now, reviewer, reason),
    )
    conn.commit()
    return int(cursor.lastrowid)


def get_rejection_count(
    conn: sqlite3.Connection,
    normalized_submitted_name: str,
    submitted_district: str | None,
    submitted_region: str | None,
    rejected_gazetteer_id: str,
) -> int:
    submitted_district = submitted_district or ""
    submitted_region = submitted_region or ""
    row = conn.execute(
        """
        SELECT rejection_count FROM rejected_candidates
        WHERE normalized_submitted_name = ? AND submitted_district = ? AND submitted_region = ?
          AND rejected_gazetteer_id = ?
        """,
        (normalized_submitted_name, submitted_district, submitted_region, rejected_gazetteer_id),
    ).fetchone()
    return int(row["rejection_count"]) if row is not None else 0


def list_review_decisions(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM review_decisions ORDER BY decision_id", conn)


def list_rejected_candidates(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM rejected_candidates ORDER BY rejection_id", conn)
