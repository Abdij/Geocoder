from __future__ import annotations

import numpy as np
import pandas as pd

from config import DEFAULT_CRS
from backend.utils import coerce_numeric, coordinate_masks, detect_column_map


ACCEPTED_STATUSES = {"auto_accepted", "accepted", "manual_accepted"}


def reviewed_match_mask(matches_df: pd.DataFrame) -> pd.Series:
    if matches_df is None or matches_df.empty:
        return pd.Series(dtype=bool)
    accept = matches_df.get("accept", False)
    reject = matches_df.get("reject", False)
    if not isinstance(accept, pd.Series):
        accept = pd.Series(False, index=matches_df.index)
    if not isinstance(reject, pd.Series):
        reject = pd.Series(False, index=matches_df.index)
    status = matches_df["status"].fillna("").astype(str).str.lower()
    return (status.isin(ACCEPTED_STATUSES) | accept.fillna(False).astype(bool)) & (
        ~reject.fillna(False).astype(bool)
    )


def normalize_review_statuses(matches_df: pd.DataFrame | None) -> pd.DataFrame:
    if matches_df is None:
        return pd.DataFrame()
    matches_df = matches_df.copy()
    if matches_df.empty:
        return matches_df
    accept_mask = matches_df.get("accept", False)
    reject_mask = matches_df.get("reject", False)
    if isinstance(accept_mask, pd.Series):
        matches_df.loc[accept_mask.fillna(False).astype(bool), "status"] = "accepted"
    if isinstance(reject_mask, pd.Series):
        matches_df.loc[reject_mask.fillna(False).astype(bool), "status"] = "rejected"
    return matches_df


def apply_geocodes(response_df: pd.DataFrame, matches_df: pd.DataFrame | None) -> pd.DataFrame:
    df = response_df.copy()
    matches_df = normalize_review_statuses(matches_df)
    columns = detect_column_map(df)
    lat_col = columns.get("latitude") or "Latitude"
    lon_col = columns.get("longitude") or "Longitude"
    if lat_col not in df.columns:
        df[lat_col] = np.nan
    if lon_col not in df.columns:
        df[lon_col] = np.nan

    metadata_defaults = {
        "Match Status": "already_geocoded",
        "Match Confidence": np.nan,
        "Match Method": "",
        "Suggested Settlement": "",
        "Suggested District": "",
        "Suggested Region": "",
    }
    for column, default in metadata_defaults.items():
        if column not in df.columns:
            df[column] = default

    accepted = matches_df[reviewed_match_mask(matches_df)] if not matches_df.empty else matches_df
    for _, match in accepted.iterrows():
        record_id = match.get("record_id")
        if pd.isna(record_id) or int(record_id) not in df.index:
            continue
        idx = int(record_id)
        df.at[idx, lat_col] = match.get("latitude")
        df.at[idx, lon_col] = match.get("longitude")
        df.at[idx, "Match Status"] = match.get("status", "accepted")
        df.at[idx, "Match Confidence"] = match.get("confidence")
        df.at[idx, "Match Method"] = match.get("matching_method")
        df.at[idx, "Suggested Settlement"] = match.get("suggested_settlement")
        df.at[idx, "Suggested District"] = match.get("suggested_district")
        df.at[idx, "Suggested Region"] = match.get("suggested_region")

    missing_mask, invalid_mask, valid_mask = coordinate_masks(df, lat_col, lon_col)
    df.loc[missing_mask | invalid_mask, "Match Status"] = df.loc[
        missing_mask | invalid_mask, "Match Status"
    ].replace({"already_geocoded": "unresolved"})
    df["_has_valid_geometry"] = valid_mask
    return df


def create_geodataframe(df: pd.DataFrame, crs: str = DEFAULT_CRS):
    columns = detect_column_map(df)
    lat_col = columns.get("latitude")
    lon_col = columns.get("longitude")
    if not lat_col or not lon_col:
        raise ValueError("Latitude and longitude columns are required to build geometry.")

    lat = coerce_numeric(df[lat_col])
    lon = coerce_numeric(df[lon_col])
    valid = lat.between(-90, 90) & lon.between(-180, 180)
    geometry_df = df.loc[valid].copy()
    if geometry_df.empty:
        raise ValueError("No valid coordinates are available for GIS export.")

    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError as error:
        raise RuntimeError("GeoPandas and Shapely are required for GIS export.") from error

    geometry = [
        Point(float(x), float(y))
        for x, y in zip(geometry_df[lon_col], geometry_df[lat_col], strict=False)
    ]
    return gpd.GeoDataFrame(geometry_df, geometry=geometry, crs=crs)
