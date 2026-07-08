from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from backend.excel_exporter import export_all_excel_outputs
from backend.geocoder import apply_geocodes
from backend.gis_exporter import export_gis_outputs
from backend.qa_report import export_qa_reports
from backend.validate_data import validate_response_data
from backend.utils import output_path
from widgets.status import metric_card


def _ensure_processed_df() -> pd.DataFrame | None:
    response_df = st.session_state.get("response_df")
    if response_df is None or response_df.empty:
        return None
    processed_df = st.session_state.get("processed_df")
    if processed_df is not None and not processed_df.empty:
        return processed_df
    matches_df = st.session_state.get("match_df")
    if matches_df is None:
        matches_df = pd.DataFrame()
    processed_df = apply_geocodes(response_df, matches_df)
    st.session_state.processed_df = processed_df
    return processed_df


def _write_log(outputs: dict[str, str], elapsed: float) -> str:
    path = output_path("ocha_processing_log.txt")
    validation = st.session_state.get("validation_report", {})
    metrics = validation.get("metrics", {}) if validation else {}
    lines = [
        "OCHA Settlement Response Processor - Processing Log",
        f"Processing time: {elapsed:.2f} seconds",
        "",
        "Validation metrics:",
    ]
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "Generated outputs:"])
    for label, output in outputs.items():
        lines.append(f"- {label}: {output}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _download_button(label: str, path: str) -> None:
    file_path = Path(path)
    if not file_path.exists():
        st.warning(f"{label} was not found at {file_path}.")
        return
    st.download_button(
        label=f"Download {label}",
        data=file_path.read_bytes(),
        file_name=file_path.name,
        mime="application/octet-stream",
        use_container_width=True,
    )


def render() -> None:
    st.markdown("### Outputs")
    st.caption("Generate cleaned Excel files, GIS layers, QA reports, and a processing log.")

    processed_df = _ensure_processed_df()
    if processed_df is None:
        st.info("Upload response data before generating outputs.")
        return

    validation_report = st.session_state.get("validation_report")
    if not validation_report:
        validation_report = validate_response_data(
            st.session_state.response_df,
            st.session_state.get("gazetteer_df"),
            st.session_state.get("boundary_gdf"),
        )
        st.session_state.validation_report = validation_report

    metrics = validation_report.get("metrics", {})
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("Processed Records", f"{len(processed_df):,}", "Ready for export", "blue")
    with col2:
        metric_card("Valid GPS", f"{metrics.get('valid_gps', 0):,}", "Original validation count", "green")
    with col3:
        review_count = 0
        matches = st.session_state.get("match_df")
        if matches is not None and not matches.empty:
            review_count = int((matches["status"] == "needs_review").sum())
        metric_card("Manual Review", f"{review_count:,}", "Remaining review rows", "yellow")
    with col4:
        metric_card("Outputs", f"{len(st.session_state.get('generated_outputs', {})):,}", "Generated files", "green")

    if st.button("Generate All Outputs", type="primary", use_container_width=True):
        started = time.perf_counter()
        outputs: dict[str, str] = {}
        errors: list[str] = []

        with st.spinner("Generating Excel workbooks..."):
            try:
                outputs.update(
                    export_all_excel_outputs(
                        processed_df,
                        st.session_state.get("match_df"),
                        validation_report,
                    )
                )
            except Exception as error:
                errors.append(f"Excel outputs: {error}")

        with st.spinner("Generating GIS layers..."):
            try:
                outputs.update(export_gis_outputs(processed_df))
            except Exception as error:
                errors.append(f"GIS outputs: {error}")

        with st.spinner("Generating QA reports..."):
            try:
                outputs.update(
                    export_qa_reports(
                        processed_df,
                        st.session_state.get("match_df"),
                        validation_report,
                        st.session_state.get("processing_seconds"),
                    )
                )
            except Exception as error:
                errors.append(f"QA reports: {error}")

        elapsed = time.perf_counter() - started
        outputs["Log File"] = _write_log(outputs, elapsed)
        st.session_state.generated_outputs = outputs
        st.session_state.output_errors = errors
        if errors:
            st.warning("Some outputs could not be generated. See details below.")
        else:
            st.success(f"All outputs generated in {elapsed:.2f} seconds.")

    errors = st.session_state.get("output_errors", [])
    for error in errors:
        st.error(error)

    outputs = st.session_state.get("generated_outputs", {})
    if outputs:
        st.markdown("#### Download Files")
        for label, path in outputs.items():
            _download_button(label, path)
    else:
        st.info("No generated outputs yet.")
