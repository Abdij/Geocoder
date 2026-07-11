from __future__ import annotations

import pandas as pd

from backend.utils import ensure_gazetteer_ids, generate_gazetteer_id


def test_generate_gazetteer_id_is_deterministic():
    first = generate_gazetteer_id("Baidoa", "Baidoa", "Bay", 3.1167, 43.65)
    second = generate_gazetteer_id("Baidoa", "Baidoa", "Bay", 3.1167, 43.65)
    assert first == second


def test_generate_gazetteer_id_ignores_case_and_whitespace_differences():
    first = generate_gazetteer_id("Baidoa", "Baidoa", "Bay", 3.1167, 43.65)
    second = generate_gazetteer_id("  BAIDOA  ", " baidoa ", "BAY", 3.1167, 43.65)
    assert first == second


def test_generate_gazetteer_id_differs_for_different_settlements():
    baidoa = generate_gazetteer_id("Baidoa", "Baidoa", "Bay", 3.1167, 43.65)
    hudur = generate_gazetteer_id("Hudur", "Hudur", "Bakool", 4.1213, 43.8990)
    assert baidoa != hudur


def test_generate_gazetteer_id_distinguishes_same_name_different_district():
    district_a = generate_gazetteer_id("Kaharey", "Doolow", "Gedo", 4.1429, 42.1907)
    district_b = generate_gazetteer_id("Kaharey", "Luuq", "Gedo", 3.9402, 42.4443)
    assert district_a != district_b


def test_ensure_gazetteer_ids_generates_for_all_rows_when_no_id_column():
    df = pd.DataFrame(
        {
            "Settlement": ["Baidoa", "Hudur"],
            "District": ["Baidoa", "Hudur"],
            "Region": ["Bay", "Bakool"],
            "Latitude": [3.1167, 4.1213],
            "Longitude": [43.65, 43.899],
        }
    )
    result = ensure_gazetteer_ids(df)
    assert "gazetteer_id" in result.columns
    assert result["gazetteer_id"].notna().all()
    assert (result["gazetteer_id"].str.strip() != "").all()
    # IDs must be distinct for distinct settlements.
    assert result["gazetteer_id"].nunique() == 2


def test_ensure_gazetteer_ids_is_stable_regardless_of_row_order():
    df = pd.DataFrame(
        {
            "Settlement": ["Baidoa", "Hudur"],
            "District": ["Baidoa", "Hudur"],
            "Region": ["Bay", "Bakool"],
            "Latitude": [3.1167, 4.1213],
            "Longitude": [43.65, 43.899],
        }
    )
    reordered = df.iloc[::-1].reset_index(drop=True)

    original_ids = set(ensure_gazetteer_ids(df)["gazetteer_id"])
    reordered_ids = set(ensure_gazetteer_ids(reordered)["gazetteer_id"])
    assert original_ids == reordered_ids


def test_ensure_gazetteer_ids_preserves_existing_partner_supplied_ids():
    df = pd.DataFrame(
        {
            "Settlement": ["Baidoa", "Hudur"],
            "District": ["Baidoa", "Hudur"],
            "Region": ["Bay", "Bakool"],
            "Latitude": [3.1167, 4.1213],
            "Longitude": [43.65, 43.899],
            "gazetteer_id": ["SOM-BAY-001", ""],
        }
    )
    result = ensure_gazetteer_ids(df)
    assert result["gazetteer_id"].iloc[0] == "SOM-BAY-001"
    # The blank second row is backfilled, not left empty.
    assert result["gazetteer_id"].iloc[1].strip() != ""
    assert result["gazetteer_id"].iloc[1] != "SOM-BAY-001"


def test_ensure_gazetteer_ids_detects_aliased_id_column_name():
    df = pd.DataFrame(
        {
            "Settlement": ["Baidoa"],
            "District": ["Baidoa"],
            "Region": ["Bay"],
            "Latitude": [3.1167],
            "Longitude": [43.65],
            "P-Code": ["SOM-BAY-001"],
        }
    )
    result = ensure_gazetteer_ids(df)
    assert "gazetteer_id" in result.columns
    assert result["gazetteer_id"].iloc[0] == "SOM-BAY-001"
