from __future__ import annotations

import os
import tempfile

import pandas as pd
import pytest

from backend.alias_repository import get_connection, list_approved_aliases, upsert_approved_alias
from backend.db_backup import (
    AliasImportError,
    export_approved_aliases,
    export_rejected_matches,
    export_review_history,
    import_aliases_from_dataframe,
    import_database_backup,
    validate_alias_import,
)
from backend.review_repository import record_rejected_candidate, record_review_decision


@pytest.fixture()
def conn():
    connection = get_connection(":memory:")
    yield connection
    connection.close()


def _seed_alias(conn, name="kaharey", gazetteer_id="gaz_abc123"):
    upsert_approved_alias(
        conn,
        normalized_submitted_name=name,
        submitted_district="doolow",
        submitted_region="gedo",
        official_gazetteer_id=gazetteer_id,
        official_settlement_name="Kaharey",
        official_district="Doolow",
        official_region="Gedo",
    )


def test_export_approved_aliases_writes_a_csv_file(conn):
    _seed_alias(conn)
    path = export_approved_aliases(conn, fmt="csv")
    try:
        assert path.exists()
        df = pd.read_csv(path)
        assert len(df) == 1
        assert df.iloc[0]["official_gazetteer_id"] == "gaz_abc123"
    finally:
        os.remove(path)


def test_export_review_history_writes_a_file(conn):
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
        confidence=96.0,
        matching_method="exact",
    )
    path = export_review_history(conn, fmt="csv")
    try:
        assert path.exists()
        df = pd.read_csv(path)
        assert len(df) == 1
    finally:
        os.remove(path)


def test_export_rejected_matches_writes_a_file(conn):
    record_rejected_candidate(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        rejected_gazetteer_id="gaz_wrong",
    )
    path = export_rejected_matches(conn, fmt="csv")
    try:
        assert path.exists()
        df = pd.read_csv(path)
        assert len(df) == 1
    finally:
        os.remove(path)


def test_validate_alias_import_rejects_missing_required_columns():
    df = pd.DataFrame({"submitted_district": ["Doolow"]})
    problems = validate_alias_import(df)
    assert any("normalized_submitted_name" in p for p in problems)
    assert any("official_gazetteer_id" in p for p in problems)


def test_validate_alias_import_rejects_empty_file():
    df = pd.DataFrame(columns=["normalized_submitted_name", "official_gazetteer_id"])
    problems = validate_alias_import(df)
    assert any("no rows" in p for p in problems)


def test_validate_alias_import_accepts_well_formed_file():
    df = pd.DataFrame({"normalized_submitted_name": ["kaharey"], "official_gazetteer_id": ["gaz_abc123"]})
    assert validate_alias_import(df) == []


def test_import_aliases_from_dataframe_raises_on_invalid_file(conn):
    df = pd.DataFrame({"some_other_column": ["x"]})
    with pytest.raises(AliasImportError):
        import_aliases_from_dataframe(conn, df)


def test_import_aliases_from_dataframe_upserts_valid_rows(conn):
    df = pd.DataFrame(
        {
            "normalized_submitted_name": ["kaharey", "baidoa"],
            "submitted_district": ["doolow", "baidoa"],
            "submitted_region": ["gedo", "bay"],
            "official_gazetteer_id": ["gaz_abc123", "gaz_def456"],
            "official_settlement_name": ["Kaharey", "Baidoa"],
        }
    )
    result = import_aliases_from_dataframe(conn, df)
    assert result["imported"] == 2
    aliases = list_approved_aliases(conn)
    assert len(aliases) == 2


def test_import_aliases_from_dataframe_merges_with_existing_history(conn):
    _seed_alias(conn)  # approval_count starts at 1
    df = pd.DataFrame(
        {
            "normalized_submitted_name": ["kaharey"],
            "submitted_district": ["doolow"],
            "submitted_region": ["gedo"],
            "official_gazetteer_id": ["gaz_abc123"],
        }
    )
    import_aliases_from_dataframe(conn, df)
    aliases = list_approved_aliases(conn)
    assert len(aliases) == 1  # merged into the existing row, not duplicated
    assert aliases.iloc[0]["approval_count"] == 2


def test_import_aliases_from_dataframe_skips_rows_missing_key_fields(conn):
    df = pd.DataFrame(
        {
            "normalized_submitted_name": ["kaharey", ""],
            "official_gazetteer_id": ["gaz_abc123", "gaz_def456"],
        }
    )
    result = import_aliases_from_dataframe(conn, df)
    assert result["imported"] == 1
    assert result["skipped"] == 1


def test_import_database_backup_merges_aliases_from_another_db(conn):
    fd, backup_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(backup_path)
    backup_conn = get_connection(backup_path)
    _seed_alias(backup_conn, name="hudur", gazetteer_id="gaz_hudur1")
    backup_conn.close()

    try:
        result = import_database_backup(conn, backup_path)
        assert result["imported"] == 1
        aliases = list_approved_aliases(conn)
        assert aliases.iloc[0]["normalized_submitted_name"] == "hudur"
    finally:
        os.remove(backup_path)


def test_import_database_backup_rejects_invalid_file(conn, tmp_path):
    bogus_path = tmp_path / "not_a_db.db"
    bogus_path.write_text("this is not a sqlite database")
    with pytest.raises(AliasImportError):
        import_database_backup(conn, bogus_path)
