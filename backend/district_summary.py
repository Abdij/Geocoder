from __future__ import annotations

import pandas as pd

from backend.utils import detect_column_map


def _value_or_default(column: str | None, fallback: str) -> str:
    return column if column else fallback


def build_summary_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    columns = detect_column_map(df)
    district_col = _value_or_default(columns.get("district"), "District")
    cluster_col = _value_or_default(columns.get("cluster"), "Cluster")
    partner_col = _value_or_default(columns.get("partner"), "Partner")
    beneficiaries_col = columns.get("beneficiaries")

    working = df.copy()
    for column in (district_col, cluster_col, partner_col):
        if column not in working.columns:
            working[column] = "Not specified"
        working[column] = working[column].fillna("Not specified").astype(str)

    if beneficiaries_col and beneficiaries_col in working.columns:
        working["_beneficiaries_numeric"] = pd.to_numeric(working[beneficiaries_col], errors="coerce").fillna(0)
    else:
        working["_beneficiaries_numeric"] = 0

    district_summary = (
        working.groupby(district_col, dropna=False)
        .agg(
            records=("_source_row_id", "count") if "_source_row_id" in working.columns else (district_col, "size"),
            settlements=(columns.get("settlement") or district_col, "nunique"),
            partners=(partner_col, "nunique"),
            clusters=(cluster_col, "nunique"),
            beneficiaries=("_beneficiaries_numeric", "sum"),
        )
        .reset_index()
        .rename(columns={district_col: "District"})
        .sort_values("District")
    )

    cluster_summary = (
        working.groupby([district_col, cluster_col], dropna=False)
        .agg(
            records=(cluster_col, "size"),
            partners=(partner_col, "nunique"),
            beneficiaries=("_beneficiaries_numeric", "sum"),
        )
        .reset_index()
        .rename(columns={district_col: "District", cluster_col: "Cluster"})
        .sort_values(["District", "Cluster"])
    )

    partner_summary = (
        working.groupby([district_col, partner_col], dropna=False)
        .agg(
            records=(partner_col, "size"),
            clusters=(cluster_col, "nunique"),
            beneficiaries=("_beneficiaries_numeric", "sum"),
        )
        .reset_index()
        .rename(columns={district_col: "District", partner_col: "Partner"})
        .sort_values(["District", "Partner"])
    )

    return {
        "district_summary": district_summary,
        "cluster_summary": cluster_summary,
        "partner_summary": partner_summary,
    }


def district_groups(df: pd.DataFrame) -> tuple[str, list[tuple[str, pd.DataFrame]]]:
    columns = detect_column_map(df)
    district_col = columns.get("district") or "District"
    working = df.copy()
    if district_col not in working.columns:
        working[district_col] = "Not specified"
    working[district_col] = working[district_col].fillna("Not specified").astype(str)
    groups = [(district, group.copy()) for district, group in working.groupby(district_col, dropna=False)]
    groups.sort(key=lambda item: item[0])
    return district_col, groups
