from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.validate_data import validate_response_data
from widgets.status import status_badge, traffic_light_card


def _ensure_validation() -> dict[str, object] | None:
    response_df = st.session_state.get("response_df")
    gazetteer_df = st.session_state.get("gazetteer_df")
    boundary_gdf = st.session_state.get("boundary_gdf")
    if response_df is None or response_df.empty:
        return None
    if "validation_report" not in st.session_state or not st.session_state.validation_report:
        st.session_state.validation_report = validate_response_data(response_df, gazetteer_df, boundary_gdf)
    return st.session_state.validation_report


def render() -> None:
    st.markdown("### Validation")
    st.caption("Review data readiness before settlement matching and export.")

    report = _ensure_validation()
    if report is None:
        st.info("Upload or load sample data to begin validation.")
        return

    if st.button("Run Validation Again", use_container_width=False):
        st.session_state.validation_report = validate_response_data(
            st.session_state.response_df,
            st.session_state.get("gazetteer_df"),
            st.session_state.get("boundary_gdf"),
        )
        report = st.session_state.validation_report

    metrics = report["metrics"]
    lights = report["traffic_lights"]
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        traffic_light_card("Total Records", f"{metrics['total_records']:,}", "blue", "Uploaded response rows")
    with col2:
        traffic_light_card("GPS Coverage", f"{metrics['gps_coverage']}%", lights["gps_coverage"], "Valid coordinates")
    with col3:
        traffic_light_card("Missing GPS", f"{metrics['missing_gps']:,}", "yellow", "Will be matched")
    with col4:
        traffic_light_card("Readiness", f"{metrics['data_readiness_score']}%", lights["readiness"], "Overall QA score")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        traffic_light_card("Duplicates", f"{metrics['duplicate_records']:,}", lights["duplicates"], "Potential repeats")
    with col6:
        traffic_light_card("Invalid Coordinates", f"{metrics['invalid_coordinates']:,}", lights["coordinates"], "Out of range")
    with col7:
        traffic_light_card("Missing Districts", f"{metrics['missing_districts']:,}", "yellow", "Admin2 gaps")
    with col8:
        traffic_light_card("Admin Hierarchy", f"{metrics['invalid_hierarchy']:,}", lights["hierarchy"], "Region-district checks")

    st.progress(float(metrics["data_readiness_score"]) / 100)

    issues = report.get("issues", [])
    st.markdown("#### Validation Issues")
    if issues:
        issue_df = pd.DataFrame(issues)
        issue_df["indicator"] = issue_df["severity"].map(
            {
                "green": status_badge("Green", "green"),
                "yellow": status_badge("Yellow", "yellow"),
                "red": status_badge("Red", "red"),
            }
        )
        st.write(issue_df[["indicator", "title", "count", "details"]].to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.success("No major validation issues detected.")

    with st.expander("Detected Column Mapping", expanded=False):
        column_map = report.get("column_map", {})
        mapping_df = pd.DataFrame(
            [{"Field": field, "Detected Column": column or "Not detected"} for field, column in column_map.items()]
        )
        st.dataframe(mapping_df, use_container_width=True, hide_index=True)
