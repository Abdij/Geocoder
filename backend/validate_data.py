from __future__ import annotations

import pandas as pd

from config import REQUIRED_GAZETTEER_FIELDS, REQUIRED_RESPONSE_FIELDS
from backend.utils import (
    coordinate_masks,
    detect_column_map,
    missing_required_fields,
    normalize_text,
    safe_percent,
    traffic_light,
)


def _issue(severity: str, title: str, count: int, details: str) -> dict[str, object]:
    return {
        "severity": severity,
        "title": title,
        "count": int(count),
        "details": details,
    }


def _missing_count(df: pd.DataFrame, column: str | None) -> int:
    if not column:
        return len(df)
    return int(df[column].isna().sum() + (df[column].astype(str).str.strip() == "").sum())


def _duplicate_count(df: pd.DataFrame, columns: list[str]) -> int:
    columns = [column for column in columns if column]
    if not columns:
        return 0
    return int(df.duplicated(subset=columns, keep=False).sum())


def validate_response_data(
    response_df: pd.DataFrame,
    gazetteer_df: pd.DataFrame | None = None,
    boundary_gdf=None,
) -> dict[str, object]:
    response_columns = detect_column_map(response_df)
    gazetteer_columns = detect_column_map(gazetteer_df) if gazetteer_df is not None else {}

    total_records = len(response_df)
    lat_col = response_columns.get("latitude")
    lon_col = response_columns.get("longitude")
    missing_gps_mask, invalid_gps_mask, valid_gps_mask = coordinate_masks(response_df, lat_col, lon_col)

    missing_settlement = _missing_count(response_df, response_columns.get("settlement"))
    missing_district = _missing_count(response_df, response_columns.get("district"))
    duplicate_subset = [
        response_columns.get("settlement"),
        response_columns.get("district"),
        response_columns.get("partner"),
        response_columns.get("cluster"),
    ]
    duplicate_records = _duplicate_count(response_df, duplicate_subset)

    invalid_hierarchy = 0
    unknown_districts = 0
    if gazetteer_df is not None and not gazetteer_df.empty:
        response_district_col = response_columns.get("district")
        response_region_col = response_columns.get("region")
        gaz_district_col = gazetteer_columns.get("district")
        gaz_region_col = gazetteer_columns.get("region")

        if response_district_col and gaz_district_col:
            known_districts = {
                normalize_text(value)
                for value in gazetteer_df[gaz_district_col].dropna().unique()
                if normalize_text(value)
            }
            response_districts = response_df[response_district_col].map(normalize_text)
            unknown_districts = int(
                ((response_districts != "") & (~response_districts.isin(known_districts))).sum()
            )

        if response_region_col and response_district_col and gaz_region_col and gaz_district_col:
            known_pairs = set(
                zip(
                    gazetteer_df[gaz_region_col].map(normalize_text),
                    gazetteer_df[gaz_district_col].map(normalize_text),
                )
            )
            response_pairs = list(
                zip(
                    response_df[response_region_col].map(normalize_text),
                    response_df[response_district_col].map(normalize_text),
                )
            )
            invalid_hierarchy = sum(
                1
                for region, district in response_pairs
                if region and district and (region, district) not in known_pairs
            )

    missing_response_fields = missing_required_fields(response_columns, REQUIRED_RESPONSE_FIELDS)
    missing_gazetteer_fields = (
        missing_required_fields(gazetteer_columns, REQUIRED_GAZETTEER_FIELDS)
        if gazetteer_df is not None
        else REQUIRED_GAZETTEER_FIELDS
    )

    issues: list[dict[str, object]] = []
    if missing_response_fields:
        issues.append(
            _issue(
                "red",
                "Missing required response columns",
                len(missing_response_fields),
                f"Add or rename these fields: {', '.join(missing_response_fields)}.",
            )
        )
    if gazetteer_df is not None and missing_gazetteer_fields:
        issues.append(
            _issue(
                "red",
                "Missing required gazetteer columns",
                len(missing_gazetteer_fields),
                f"Gazetteer needs: {', '.join(missing_gazetteer_fields)}.",
            )
        )
    if int(missing_gps_mask.sum()):
        issues.append(
            _issue(
                "yellow",
                "Records missing GPS coordinates",
                int(missing_gps_mask.sum()),
                "These records will be sent to settlement matching.",
            )
        )
    if int(invalid_gps_mask.sum()):
        issues.append(
            _issue(
                "red",
                "Invalid coordinates",
                int(invalid_gps_mask.sum()),
                "Latitude must be -90 to 90 and longitude must be -180 to 180.",
            )
        )
    if missing_settlement:
        issues.append(
            _issue(
                "red",
                "Missing settlement names",
                missing_settlement,
                "Settlement names are required for automated matching.",
            )
        )
    if missing_district:
        issues.append(
            _issue(
                "yellow",
                "Missing districts",
                missing_district,
                "Districts improve matching confidence and summary generation.",
            )
        )
    if duplicate_records:
        issues.append(
            _issue(
                "yellow",
                "Potential duplicate records",
                duplicate_records,
                "Duplicates are based on settlement, district, partner, and cluster where available.",
            )
        )
    if unknown_districts:
        issues.append(
            _issue(
                "yellow",
                "Districts not found in gazetteer",
                unknown_districts,
                "Review spelling variations or gazetteer coverage.",
            )
        )
    if invalid_hierarchy:
        issues.append(
            _issue(
                "red",
                "Invalid administrative hierarchy",
                invalid_hierarchy,
                "Some region-district combinations do not appear in the gazetteer.",
            )
        )

    gps_coverage = safe_percent(int(valid_gps_mask.sum()), total_records)
    missing_gps = int(missing_gps_mask.sum())
    invalid_coordinates = int(invalid_gps_mask.sum())

    penalty = 0
    penalty += min(35, len(missing_response_fields) * 15)
    penalty += min(25, int(missing_gps_mask.sum()) / max(total_records, 1) * 25)
    penalty += min(20, invalid_coordinates / max(total_records, 1) * 20)
    penalty += min(10, duplicate_records / max(total_records, 1) * 10)
    penalty += min(10, (unknown_districts + invalid_hierarchy) / max(total_records, 1) * 10)
    readiness_score = max(0, round(100 - penalty, 1))

    return {
        "column_map": response_columns,
        "gazetteer_column_map": gazetteer_columns,
        "metrics": {
            "total_records": total_records,
            "gps_coverage": gps_coverage,
            "valid_gps": int(valid_gps_mask.sum()),
            "missing_gps": missing_gps,
            "duplicate_records": duplicate_records,
            "invalid_coordinates": invalid_coordinates,
            "missing_settlements": missing_settlement,
            "missing_districts": missing_district,
            "unknown_districts": unknown_districts,
            "invalid_hierarchy": invalid_hierarchy,
            "boundary_features": int(len(boundary_gdf)) if boundary_gdf is not None else 0,
            "data_readiness_score": readiness_score,
        },
        "traffic_lights": {
            "gps_coverage": traffic_light(gps_coverage, 90, 70),
            "duplicates": traffic_light(duplicate_records, 0, max(5, total_records * 0.03), False),
            "coordinates": traffic_light(invalid_coordinates, 0, max(3, total_records * 0.02), False),
            "hierarchy": traffic_light(invalid_hierarchy, 0, max(3, total_records * 0.02), False),
            "readiness": traffic_light(readiness_score, 85, 70),
        },
        "issues": issues,
        "masks": {
            "missing_gps": missing_gps_mask,
            "invalid_gps": invalid_gps_mask,
            "valid_gps": valid_gps_mask,
        },
    }
