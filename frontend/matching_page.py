from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from backend.settlement_matcher import match_records, matching_statistics
from widgets.status import metric_card


def render() -> None:
    st.markdown("### AI Settlement Matching")
    st.caption("Find coordinates for records with missing or invalid GPS values.")

    response_df = st.session_state.get("response_df")
    gazetteer_df = st.session_state.get("gazetteer_df")
    if response_df is None or response_df.empty or gazetteer_df is None or gazetteer_df.empty:
        st.info("Upload response data and a settlement gazetteer before running matching.")
        return

    settings_col, run_col = st.columns([2, 1], gap="large")
    with settings_col:
        use_semantic = st.checkbox(
            "Use sentence-transformer semantic matching",
            value=False,
            help="Optional local model step for ambiguous settlement names. First run may download or load a local model.",
        )
        use_ollama = st.checkbox(
            "Use local Ollama reasoning for ambiguous matches",
            value=False,
            help="Requires Ollama running locally with a Qwen model available.",
        )
    with run_col:
        run_button = st.button("Run Settlement Matching", type="primary", use_container_width=True)

    if run_button:
        progress = st.progress(0)
        status_line = st.empty()
        started = time.perf_counter()

        def update_progress(done: int, total: int, label: str) -> None:
            progress.progress(min(done / max(total, 1), 1.0))
            status_line.caption(f"{done:,} of {total:,}: {label}")

        try:
            with st.spinner("Matching settlements against gazetteer..."):
                matches_df = match_records(
                    response_df,
                    gazetteer_df,
                    use_semantic=use_semantic,
                    use_ollama=use_ollama,
                    progress_callback=update_progress,
                )
            elapsed = time.perf_counter() - started
            st.session_state.match_df = matches_df
            st.session_state.processing_seconds = elapsed
            st.session_state.processed_df = pd.DataFrame()
            progress.progress(1.0)
            status_line.caption(f"Completed matching in {elapsed:.2f} seconds.")
            st.success("Settlement matching completed.")
        except Exception as error:
            st.error(f"Matching could not be completed: {error}")

    matches_df = st.session_state.get("match_df")
    if matches_df is not None and not matches_df.empty:
        stats = matching_statistics(matches_df)
        cols = st.columns(5)
        with cols[0]:
            metric_card("Matched", f"{stats['matched']:,}", "Auto or review candidates", "green")
        with cols[1]:
            metric_card("Auto Accepted", f"{stats['auto_accepted']:,}", ">= 90% confidence", "green")
        with cols[2]:
            metric_card("Needs Review", f"{stats['needs_review']:,}", "75-89% confidence", "yellow")
        with cols[3]:
            metric_card("Unresolved", f"{stats['unresolved']:,}", "< 75% confidence", "red")
        with cols[4]:
            metric_card("Avg Confidence", f"{stats['average_confidence']}%", "Candidate quality", "blue")

        st.markdown("#### Matching Results")
        st.dataframe(matches_df, use_container_width=True, hide_index=True)
    else:
        st.info("No matching results yet. Run settlement matching to populate the review table.")
