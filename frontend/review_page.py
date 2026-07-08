from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from backend.geocoder import apply_geocodes, normalize_review_statuses
from backend.map_generator import create_response_map


def _render_map(processed_df: pd.DataFrame, matches_df: pd.DataFrame) -> None:
    try:
        response_map = create_response_map(
            processed_df,
            st.session_state.get("boundary_gdf"),
            matches_df,
        )
        try:
            from streamlit_folium import st_folium

            st_folium(response_map, use_container_width=True, height=560)
        except ImportError:
            components.html(response_map._repr_html_(), height=580)
    except Exception as error:
        st.warning(f"Map preview is unavailable: {error}")


def render() -> None:
    st.markdown("### Human Review")
    st.caption("Accept high-confidence suggestions, reject weak matches, or edit coordinates before export.")

    response_df = st.session_state.get("response_df")
    matches_df = st.session_state.get("match_df")
    if response_df is None or response_df.empty:
        st.info("Upload response data before reviewing matches.")
        return
    if matches_df is None or matches_df.empty:
        st.info("Run settlement matching before using the review table.")
        return

    st.markdown("#### Editable Match Review Table")
    edited_df = st.data_editor(
        matches_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["auto_accepted", "accepted", "needs_review", "unresolved", "manual_accepted", "rejected"],
            ),
            "accept": st.column_config.CheckboxColumn("Accept"),
            "reject": st.column_config.CheckboxColumn("Reject"),
            "confidence": st.column_config.NumberColumn("Confidence", min_value=0, max_value=100, step=0.1),
            "latitude": st.column_config.NumberColumn("Latitude", format="%.6f"),
            "longitude": st.column_config.NumberColumn("Longitude", format="%.6f"),
        },
        disabled=[
            "record_id",
            "source_row",
            "submitted_settlement",
            "submitted_district",
            "submitted_region",
            "matching_method",
            "reason",
        ],
        key="review_editor",
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("Save Review Decisions", use_container_width=True):
            st.session_state.match_df = normalize_review_statuses(edited_df)
            st.success("Review decisions saved.")
    with col_b:
        if st.button("Apply Geocodes", type="primary", use_container_width=True):
            normalized = normalize_review_statuses(edited_df)
            st.session_state.match_df = normalized
            st.session_state.processed_df = apply_geocodes(response_df, normalized)
            st.success("Accepted coordinates applied to the response records.")

    processed_df = st.session_state.get("processed_df")
    if processed_df is None or processed_df.empty:
        preview_df = apply_geocodes(response_df, normalize_review_statuses(edited_df))
    else:
        preview_df = processed_df

    st.markdown("#### Live Map Preview")
    _render_map(preview_df, normalize_review_statuses(edited_df))

    with st.expander("Processed Data Preview", expanded=False):
        st.dataframe(preview_df.head(100), use_container_width=True, hide_index=True)
