from __future__ import annotations

import pytest

from backend.alias_repository import (
    deactivate_alias,
    find_active_alias,
    get_connection,
    list_approved_aliases,
    upsert_approved_alias,
)


@pytest.fixture()
def conn():
    connection = get_connection(":memory:")
    yield connection
    connection.close()


def test_new_alias_starts_with_approval_count_one(conn):
    alias_id = upsert_approved_alias(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        official_gazetteer_id="gaz_abc123",
        official_settlement_name="Kaharey",
        official_district="Doolow",
        official_region="Gedo",
        approved_by="analyst1",
        source_partner="UNHCR",
    )
    aliases = list_approved_aliases(conn)
    assert len(aliases) == 1
    assert aliases.iloc[0]["alias_id"] == alias_id
    assert aliases.iloc[0]["approval_count"] == 1
    assert aliases.iloc[0]["active"] == 1


def test_repeated_approval_increments_count_instead_of_duplicating(conn):
    for _ in range(3):
        upsert_approved_alias(
            conn,
            normalized_submitted_name="kaharey",
            submitted_district="doolow",
            submitted_region="gedo",
            official_gazetteer_id="gaz_abc123",
            official_settlement_name="Kaharey",
            official_district="Doolow",
            official_region="Gedo",
        )
    aliases = list_approved_aliases(conn)
    assert len(aliases) == 1
    assert aliases.iloc[0]["approval_count"] == 3


def test_different_gazetteer_id_creates_a_separate_alias_row(conn):
    upsert_approved_alias(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        official_gazetteer_id="gaz_abc123",
        official_settlement_name="Kaharey",
        official_district="Doolow",
        official_region="Gedo",
    )
    upsert_approved_alias(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="luuq",
        submitted_region="gedo",
        official_gazetteer_id="gaz_def456",
        official_settlement_name="Kaharey",
        official_district="Luuq",
        official_region="Gedo",
    )
    aliases = list_approved_aliases(conn)
    assert len(aliases) == 2


def test_find_active_alias_exact_context_match(conn):
    upsert_approved_alias(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        official_gazetteer_id="gaz_abc123",
        official_settlement_name="Kaharey",
        official_district="Doolow",
        official_region="Gedo",
    )
    found = find_active_alias(conn, "kaharey", "doolow", "gedo")
    assert found is not None
    assert found["official_gazetteer_id"] == "gaz_abc123"


def test_find_active_alias_falls_back_when_region_unknown(conn):
    upsert_approved_alias(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        official_gazetteer_id="gaz_abc123",
        official_settlement_name="Kaharey",
        official_district="Doolow",
        official_region="Gedo",
    )
    # Submitted region is missing/unknown for this record, but district still matches.
    found = find_active_alias(conn, "kaharey", "doolow", "")
    assert found is not None
    assert found["official_gazetteer_id"] == "gaz_abc123"


def test_find_active_alias_returns_none_when_no_match(conn):
    assert find_active_alias(conn, "nonexistent-place") is None


def test_deactivated_alias_is_not_returned(conn):
    alias_id = upsert_approved_alias(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        official_gazetteer_id="gaz_abc123",
        official_settlement_name="Kaharey",
        official_district="Doolow",
        official_region="Gedo",
    )
    deactivate_alias(conn, alias_id)
    assert find_active_alias(conn, "kaharey", "doolow", "gedo") is None


def test_ambiguous_district_prefers_highest_approval_count(conn):
    upsert_approved_alias(
        conn,
        normalized_submitted_name="kaharey",
        submitted_district="doolow",
        submitted_region="gedo",
        official_gazetteer_id="gaz_low",
        official_settlement_name="Kaharey",
        official_district="Doolow",
        official_region="Gedo",
    )
    for _ in range(4):
        upsert_approved_alias(
            conn,
            normalized_submitted_name="kaharey",
            submitted_district="doolow",
            submitted_region="",
            official_gazetteer_id="gaz_high",
            official_settlement_name="Kaharey",
            official_district="Doolow",
            official_region="Gedo",
        )
    found = find_active_alias(conn, "kaharey", "doolow", "unknown-region")
    assert found["official_gazetteer_id"] == "gaz_high"
