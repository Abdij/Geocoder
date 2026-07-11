from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.alias_repository import get_connection, list_approved_aliases, upsert_approved_alias
from backend.review_repository import list_rejected_candidates, list_review_decisions
from backend.utils import output_path
from config import PLACE_INTELLIGENCE_DB_PATH

REQUIRED_ALIAS_IMPORT_COLUMNS = {"normalized_submitted_name", "official_gazetteer_id"}


class AliasImportError(ValueError):
    """Raised when an alias import file or database backup fails validation."""


def _export(df: pd.DataFrame, filename_stem: str, fmt: str) -> Path:
    fmt = fmt.lower()
    if fmt not in {"csv", "xlsx"}:
        raise ValueError(f"Unsupported export format: {fmt}")
    path = output_path(f"{filename_stem}.{fmt}")
    if fmt == "xlsx":
        df.to_excel(path, index=False, engine="xlsxwriter")
    else:
        df.to_csv(path, index=False)
    return path


def export_approved_aliases(conn: sqlite3.Connection, fmt: str = "csv") -> Path:
    return _export(list_approved_aliases(conn), "approved_aliases", fmt)


def export_review_history(conn: sqlite3.Connection, fmt: str = "csv") -> Path:
    return _export(list_review_decisions(conn), "review_history", fmt)


def export_rejected_matches(conn: sqlite3.Connection, fmt: str = "csv") -> Path:
    return _export(list_rejected_candidates(conn), "rejected_candidates", fmt)


def export_database_backup() -> Path:
    """Copy the raw place-intelligence SQLite file for download/backup.

    If no database has been created yet (e.g. a fresh install with no
    matches run), still returns a valid empty backup rather than erroring.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = output_path(f"place_intelligence_backup_{timestamp}.db")
    if PLACE_INTELLIGENCE_DB_PATH.exists():
        shutil.copy2(PLACE_INTELLIGENCE_DB_PATH, path)
    else:
        get_connection(path).close()
    return path


def validate_alias_import(df: pd.DataFrame) -> list[str]:
    """Return a list of problems with an alias import file, empty if it's valid."""
    problems = []
    missing = REQUIRED_ALIAS_IMPORT_COLUMNS - set(df.columns)
    if missing:
        problems.append(f"Missing required columns: {', '.join(sorted(missing))}")
    if df.empty:
        problems.append("The file has no rows.")
    return problems


def import_aliases_from_dataframe(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    approved_by: str | None = None,
) -> dict[str, int]:
    """Import approved aliases from an uploaded CSV/Excel, upserting each row.

    Raises AliasImportError if the file fails validation, before touching
    the database. Never silently drops or overwrites existing alias
    history - upsert_approved_alias() only ever increments approval_count
    for an existing (name, district, region, gazetteer_id) match or adds a
    new row, the same path a normal analyst approval takes.
    """
    problems = validate_alias_import(df)
    if problems:
        raise AliasImportError("; ".join(problems))

    imported = 0
    for _, row in df.iterrows():
        normalized_name = str(row.get("normalized_submitted_name", "")).strip()
        gazetteer_id = str(row.get("official_gazetteer_id", "")).strip()
        if not normalized_name or not gazetteer_id:
            continue
        upsert_approved_alias(
            conn,
            normalized_submitted_name=normalized_name,
            submitted_district=row.get("submitted_district"),
            submitted_region=row.get("submitted_region"),
            official_gazetteer_id=gazetteer_id,
            official_settlement_name=row.get("official_settlement_name"),
            official_district=row.get("official_district"),
            official_region=row.get("official_region"),
            approved_by=approved_by or row.get("approved_by"),
            source_partner=row.get("source_partner"),
        )
        imported += 1
    return {"imported": imported, "skipped": len(df) - imported}


def import_database_backup(conn: sqlite3.Connection, backup_path: Path) -> dict[str, int]:
    """Merge an uploaded place-intelligence database backup's aliases into the current one.

    Only the approved_aliases table is merged (the durable "trained" state
    worth carrying over between machines/backups) via the same upsert path
    normal approvals use, so approval counts combine correctly rather than
    being silently overwritten.
    """
    backup_conn = sqlite3.connect(str(backup_path))
    backup_conn.row_factory = sqlite3.Row
    try:
        aliases = pd.read_sql_query("SELECT * FROM approved_aliases WHERE active = 1", backup_conn)
    except Exception as error:
        raise AliasImportError(f"Not a valid place-intelligence backup file: {error}") from error
    finally:
        backup_conn.close()

    return import_aliases_from_dataframe(conn, aliases)
