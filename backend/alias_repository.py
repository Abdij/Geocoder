from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import PLACE_INTELLIGENCE_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_submitted_name TEXT NOT NULL,
    submitted_district TEXT NOT NULL DEFAULT '',
    submitted_region TEXT NOT NULL DEFAULT '',
    official_gazetteer_id TEXT NOT NULL,
    official_settlement_name TEXT,
    official_district TEXT,
    official_region TEXT,
    approval_count INTEGER NOT NULL DEFAULT 1,
    first_approved_at TEXT NOT NULL,
    last_approved_at TEXT NOT NULL,
    approved_by TEXT,
    source_partner TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_approved_aliases_lookup
    ON approved_aliases (normalized_submitted_name, submitted_district, submitted_region, active);

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER,
    run_id TEXT,
    submitted_name TEXT,
    submitted_district TEXT,
    submitted_region TEXT,
    suggested_gazetteer_id TEXT,
    final_gazetteer_id TEXT,
    decision TEXT,
    confidence REAL,
    matching_method TEXT,
    reviewer TEXT,
    reviewed_at TEXT NOT NULL,
    reviewer_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_decisions_record ON review_decisions (record_id, run_id);

CREATE TABLE IF NOT EXISTS rejected_candidates (
    rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_submitted_name TEXT NOT NULL,
    submitted_district TEXT NOT NULL DEFAULT '',
    submitted_region TEXT NOT NULL DEFAULT '',
    rejected_gazetteer_id TEXT NOT NULL,
    rejection_count INTEGER NOT NULL DEFAULT 1,
    last_rejected_at TEXT NOT NULL,
    reviewer TEXT,
    reason TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rejected_candidates_unique
    ON rejected_candidates (normalized_submitted_name, submitted_district, submitted_region, rejected_gazetteer_id);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialize_database(conn: sqlite3.Connection) -> None:
    """Create the approved_aliases, review_decisions, and rejected_candidates tables if missing."""
    conn.executescript(_SCHEMA)
    conn.commit()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open the local place-intelligence SQLite database, creating it on first use.

    Pass db_path=":memory:" for an isolated in-memory database (used by tests).
    """
    if db_path is None:
        db_path = PLACE_INTELLIGENCE_DB_PATH

    if db_path != ":memory:":
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(path)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    initialize_database(conn)
    return conn


def upsert_approved_alias(
    conn: sqlite3.Connection,
    *,
    normalized_submitted_name: str,
    submitted_district: str | None,
    submitted_region: str | None,
    official_gazetteer_id: str,
    official_settlement_name: str | None,
    official_district: str | None,
    official_region: str | None,
    approved_by: str | None = None,
    source_partner: str | None = None,
) -> int:
    """Record an analyst-approved alias.

    Only ever called from confirmed analyst acceptances (see geocoder.apply_geocodes
    / the review workflow) - never from a raw, unreviewed model suggestion. Repeating
    the same (name, district, region) -> gazetteer_id combination increments
    approval_count instead of creating a duplicate row.
    """
    submitted_district = submitted_district or ""
    submitted_region = submitted_region or ""
    now = utcnow()

    existing = conn.execute(
        """
        SELECT alias_id, approval_count FROM approved_aliases
        WHERE normalized_submitted_name = ? AND submitted_district = ? AND submitted_region = ?
          AND official_gazetteer_id = ? AND active = 1
        """,
        (normalized_submitted_name, submitted_district, submitted_region, official_gazetteer_id),
    ).fetchone()

    if existing is not None:
        conn.execute(
            """
            UPDATE approved_aliases
            SET approval_count = ?, last_approved_at = ?,
                approved_by = COALESCE(?, approved_by), source_partner = COALESCE(?, source_partner)
            WHERE alias_id = ?
            """,
            (existing["approval_count"] + 1, now, approved_by, source_partner, existing["alias_id"]),
        )
        conn.commit()
        return int(existing["alias_id"])

    cursor = conn.execute(
        """
        INSERT INTO approved_aliases (
            normalized_submitted_name, submitted_district, submitted_region,
            official_gazetteer_id, official_settlement_name, official_district, official_region,
            approval_count, first_approved_at, last_approved_at, approved_by, source_partner, active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 1)
        """,
        (
            normalized_submitted_name,
            submitted_district,
            submitted_region,
            official_gazetteer_id,
            official_settlement_name,
            official_district,
            official_region,
            now,
            now,
            approved_by,
            source_partner,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def find_active_alias(
    conn: sqlite3.Connection,
    normalized_submitted_name: str,
    submitted_district: str | None = None,
    submitted_region: str | None = None,
) -> dict[str, Any] | None:
    """Look up the strongest active approved alias for a submitted name.

    Tries an exact (name, district, region) match first, then (name, district)
    ignoring region, then name alone - each level preferring the alias with
    the highest approval_count, then the most recently approved.
    """
    submitted_district = submitted_district or ""
    submitted_region = submitted_region or ""

    lookups: list[tuple[str, str | None, str | None]] = [
        (normalized_submitted_name, submitted_district, submitted_region),
        (normalized_submitted_name, submitted_district, None),
        (normalized_submitted_name, None, None),
    ]
    for name, district, region in lookups:
        query = "SELECT * FROM approved_aliases WHERE normalized_submitted_name = ? AND active = 1"
        params: list[Any] = [name]
        if district is not None:
            query += " AND submitted_district = ?"
            params.append(district)
        if region is not None:
            query += " AND submitted_region = ?"
            params.append(region)
        query += " ORDER BY approval_count DESC, last_approved_at DESC LIMIT 1"
        row = conn.execute(query, params).fetchone()
        if row is not None:
            return dict(row)
    return None


def deactivate_alias(conn: sqlite3.Connection, alias_id: int) -> None:
    conn.execute("UPDATE approved_aliases SET active = 0 WHERE alias_id = ?", (alias_id,))
    conn.commit()


def list_approved_aliases(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM approved_aliases ORDER BY alias_id", conn)
