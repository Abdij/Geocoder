from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from backend.load_data import DataLoadError, load_sample_datasets, read_spatial_file, read_tabular_file
from backend.validate_data import validate_response_data
from config import SUPPORTED_SPATIAL_EXTENSIONS
from widgets.status import metric_card


def _gazetteer_from_upload(uploaded_file) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix in SUPPORTED_SPATIAL_EXTENSIONS:
        gdf = read_spatial_file(uploaded_file)
        df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))
        if "geometry" in gdf and gdf.geometry.notna().any():
            points = gdf.geometry.to_crs("EPSG:4326").representative_point() if gdf.crs else gdf.geometry.representative_point()
            if "Latitude" not in df.columns:
                df["Latitude"] = points.y
            if "Longitude" not in df.columns:
                df["Longitude"] = points.x
        return df
    return read_tabular_file(uploaded_file, add_row_ids=False)


def _load_uploaded(response_upload, gazetteer_upload, boundary_upload) -> None:
    response_df = read_tabular_file(response_upload)
    gazetteer_df = _gazetteer_from_upload(gazetteer_upload)
    boundary_gdf = read_spatial_file(boundary_upload) if boundary_upload is not None else None

    st.session_state.response_df = response_df
    st.session_state.gazetteer_df = gazetteer_df
    st.session_state.boundary_gdf = boundary_gdf
    st.session_state.validation_report = validate_response_data(response_df, gazetteer_df, boundary_gdf)
    st.session_state.match_df = pd.DataFrame()
    st.session_state.processed_df = pd.DataFrame()
    st.session_state.generated_outputs = {}


def render() -> None:
    st.markdown("### Upload Data")
    st.caption("Load partner response records, a settlement gazetteer, and optional district boundaries.")

    left, right = st.columns([2, 1], gap="large")
    with left:
        response_upload = st.file_uploader(
            "Response Excel or CSV",
            type=["xlsx", "xls", "csv"],
            help="Partner response data at settlement level.",
        )
        gazetteer_upload = st.file_uploader(
            "Settlement Gazetteer",
            type=["xlsx", "xls", "csv", "geojson", "json", "gpkg", "zip"],
            help="Must include settlement name, district, latitude, and longitude.",
        )
        boundary_upload = st.file_uploader(
            "District Boundary Layer",
            type=["geojson", "json", "gpkg", "zip"],
            help="Optional district boundaries for map context.",
        )

        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Load Uploaded Files", type="primary", use_container_width=True):
                if response_upload is None or gazetteer_upload is None:
                    st.error("Upload both a response file and a settlement gazetteer.")
                else:
                    try:
                        _load_uploaded(response_upload, gazetteer_upload, boundary_upload)
                        st.success("Files loaded and validated.")
                    except DataLoadError as error:
                        st.error(str(error))
                    except Exception as error:
                        st.error(f"Could not load the files: {error}")
        with col_b:
            if st.button("Load Sample Data", use_container_width=True):
                try:
                    response_df, gazetteer_df, boundary_gdf = load_sample_datasets()
                    st.session_state.response_df = response_df
                    st.session_state.gazetteer_df = gazetteer_df
                    st.session_state.boundary_gdf = boundary_gdf
                    st.session_state.validation_report = validate_response_data(response_df, gazetteer_df, boundary_gdf)
                    st.session_state.match_df = pd.DataFrame()
                    st.session_state.processed_df = pd.DataFrame()
                    st.session_state.generated_outputs = {}
                    st.success("Sample data loaded.")
                except Exception as error:
                    st.error(f"Could not load sample data: {error}")

    with right:
        metric_card("Expected Records", "100,000+", "Designed for monthly partner files", "blue")
        metric_card("Processing Mode", "Local", "No cloud service required", "green")
        metric_card("Review Control", "Human-in-loop", "Accept, reject, or edit uncertain matches", "yellow")

    if "response_df" in st.session_state and not st.session_state.response_df.empty:
        st.markdown("#### Loaded Data Preview")
        preview_cols = st.columns(3)
        preview_cols[0].metric("Response records", f"{len(st.session_state.response_df):,}")
        preview_cols[1].metric("Gazetteer rows", f"{len(st.session_state.gazetteer_df):,}")
        preview_cols[2].metric(
            "Boundary features",
            f"{len(st.session_state.boundary_gdf):,}" if st.session_state.boundary_gdf is not None else "0",
        )
        st.dataframe(st.session_state.response_df.head(30), use_container_width=True, hide_index=True)
