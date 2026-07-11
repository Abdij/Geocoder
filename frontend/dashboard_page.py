from __future__ import annotations

import base64
import html
import importlib.util
import time
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from backend.alias_repository import get_connection
from backend.audit_logger import export_audit_csv, export_audit_excel
from backend.confidence_scorer import ADMIN_CONTRADICTION_THRESHOLD
from backend.excel_exporter import export_all_excel_outputs
from backend.geocoder import apply_geocodes, normalize_review_statuses
from backend.gis_exporter import export_gis_outputs
from backend.load_data import DataLoadError, load_sample_datasets, read_spatial_file, read_tabular_file
from backend.map_generator import create_response_map
from backend.qa_report import export_qa_excel_report, export_qa_pdf_report
from backend.review_repository import list_review_decisions
from backend.settlement_matcher import match_records, matching_statistics
from backend.utils import detect_column_map, output_path, safe_percent
from backend.validate_data import validate_response_data
from config import (
    APP_NAME,
    APP_TAGLINE,
    ASSETS_DIR,
    MAX_AUTO_ACCEPT_DISTANCE_KM,
    STATIC_DIR,
    STATUS_COLORS,
    SUPPORTED_SPATIAL_EXTENSIONS,
)


OUTPUT_ITEMS = [
    ("District Data Sheets", "District Workbook", "District-level workbook"),
    ("District Summary Sheet", "District Summary", "Summary at district level"),
    ("Cleaned Response Data", "Cleaned Excel", "Excel format"),
    ("Settlement Shapefile", "Shapefile ZIP", "ESRI Shapefile ZIP"),
    ("GeoPackage", "GeoPackage", "GIS format .gpkg"),
    ("GeoJSON", "GeoJSON", "Web GIS format"),
    ("QA Excel Report", "QA Excel Report", "Detailed QA workbook"),
    ("QA / Matching Report", "QA PDF Report", "Matched, unmatched, stats"),
    ("Audit Log (CSV)", "Audit Log CSV", "Full matching + review audit trail"),
    ("Audit Log (Excel)", "Audit Log Excel", "Full matching + review audit trail"),
]
OUTPUT_TITLES = [title for title, _, _ in OUTPUT_ITEMS]
OUTPUT_KEY_BY_TITLE = {title: key for title, key, _ in OUTPUT_ITEMS}
EXCEL_OUTPUT_KEYS = {"Cleaned Excel", "District Workbook", "District Summary"}
AUDIT_OUTPUT_KEYS = {"Audit Log CSV", "Audit Log Excel"}
GIS_OUTPUT_KEYS = {"Shapefile ZIP", "GeoPackage", "GeoJSON"}
DASHBOARD_MAP_HEIGHT = 880


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _html(markup: str) -> None:
    cleaned = "\n".join(line.strip() for line in markup.strip().splitlines())
    st.markdown(cleaned, unsafe_allow_html=True)


def _file_icon() -> str:
    mark_path = ASSETS_DIR / "ocha_mark.svg"
    if not mark_path.exists():
        return ""
    encoded = base64.b64encode(mark_path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _state_defaults() -> None:
    defaults = {
        "response_df": pd.DataFrame(),
        "gazetteer_df": pd.DataFrame(),
        "boundary_gdf": None,
        "validation_report": {},
        "match_df": pd.DataFrame(),
        "processed_df": pd.DataFrame(),
        "generated_outputs": {},
        "output_errors": [],
        "output_setup_notice": "",
        "output_stage_timings": [],
        "processing_seconds": None,
        "source_files": {},
        "use_semantic": False,
        "use_ollama": False,
        "matching_warnings": [],
        "selected_output_titles": OUTPUT_TITLES.copy(),
        "download_cache": {},
        "map_cache": {},
        "data_revision": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_generated_outputs() -> None:
    st.session_state.generated_outputs = {}
    st.session_state.output_errors = []
    st.session_state.output_setup_notice = ""
    st.session_state.output_stage_timings = []
    st.session_state.download_cache = {}


def _bump_data_revision() -> None:
    st.session_state.data_revision = int(st.session_state.get("data_revision", 0)) + 1
    st.session_state.map_cache = {}
    st.session_state.download_cache = {}


def _selected_output_keys() -> set[str]:
    selected_titles = st.session_state.get("selected_output_titles") or OUTPUT_TITLES
    return {
        OUTPUT_KEY_BY_TITLE[title]
        for title in selected_titles
        if title in OUTPUT_KEY_BY_TITLE
    }


def _download_bytes(file_path: Path) -> bytes:
    stat = file_path.stat()
    cache_key = str(file_path)
    cache = st.session_state.setdefault("download_cache", {})
    cached = cache.get(cache_key)
    if (
        cached
        and cached.get("mtime_ns") == stat.st_mtime_ns
        and cached.get("size") == stat.st_size
    ):
        return cached["data"]
    data = file_path.read_bytes()
    cache[cache_key] = {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "data": data,
    }
    return data


def _reset_workflow() -> None:
    for key in (
        "response_df",
        "gazetteer_df",
        "validation_report",
        "match_df",
        "processed_df",
        "generated_outputs",
        "output_errors",
        "output_setup_notice",
        "output_stage_timings",
        "processing_seconds",
        "source_files",
        "matching_warnings",
        "download_cache",
        "map_cache",
    ):
        if key in ("response_df", "gazetteer_df", "match_df", "processed_df"):
            st.session_state[key] = pd.DataFrame()
        elif key == "source_files":
            st.session_state[key] = {}
        elif key in ("output_errors", "matching_warnings", "output_stage_timings"):
            st.session_state[key] = []
        elif key == "output_setup_notice":
            st.session_state[key] = ""
        else:
            st.session_state[key] = None if key == "processing_seconds" else {}
    st.session_state.boundary_gdf = None
    _bump_data_revision()


def _gazetteer_from_upload(uploaded_file) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix in SUPPORTED_SPATIAL_EXTENSIONS:
        gdf = read_spatial_file(uploaded_file)
        df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))
        if "geometry" in gdf and gdf.geometry.notna().any():
            points = (
                gdf.geometry.to_crs("EPSG:4326").representative_point()
                if gdf.crs
                else gdf.geometry.representative_point()
            )
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
    _clear_generated_outputs()
    _bump_data_revision()
    st.session_state.source_files = {
        "response": response_upload.name,
        "gazetteer": gazetteer_upload.name,
        "boundaries": boundary_upload.name if boundary_upload is not None else "Not loaded",
    }


def _load_sample() -> None:
    response_df, gazetteer_df, boundary_gdf = load_sample_datasets()
    st.session_state.response_df = response_df
    st.session_state.gazetteer_df = gazetteer_df
    st.session_state.boundary_gdf = boundary_gdf
    st.session_state.validation_report = validate_response_data(response_df, gazetteer_df, boundary_gdf)
    st.session_state.match_df = pd.DataFrame()
    st.session_state.processed_df = pd.DataFrame()
    _clear_generated_outputs()
    _bump_data_revision()
    st.session_state.source_files = {
        "response": "sample_response.csv",
        "gazetteer": "sample_settlement_gazetteer.csv",
        "boundaries": "sample_district_boundaries.geojson",
    }


def _has_data() -> bool:
    response_df = st.session_state.get("response_df")
    return response_df is not None and not response_df.empty


def _ensure_validation() -> dict[str, object]:
    if not _has_data():
        return {}
    if not st.session_state.get("validation_report"):
        st.session_state.validation_report = validate_response_data(
            st.session_state.response_df,
            st.session_state.get("gazetteer_df"),
            st.session_state.get("boundary_gdf"),
        )
    return st.session_state.validation_report


def _package_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _rapidfuzz_available() -> bool:
    return _package_available("rapidfuzz")


def _semantic_available() -> bool:
    return _package_available("sentence_transformers")


def _reportlab_available() -> bool:
    return _package_available("reportlab")


def _ollama_available(timeout: float = 2.0) -> bool:
    try:
        import requests

        response = requests.get("http://localhost:11434/api/tags", timeout=timeout)
        return response.ok
    except Exception:
        return False


def _run_matching() -> None:
    warnings: list[str] = []
    response_df = st.session_state.get("response_df")
    gazetteer_df = st.session_state.get("gazetteer_df")
    if response_df is None or response_df.empty or gazetteer_df is None or gazetteer_df.empty:
        warnings.append("Load response data and a settlement gazetteer first.")
        st.session_state.matching_warnings = warnings
        return

    use_semantic = st.session_state.get("use_semantic", False)
    use_ollama = st.session_state.get("use_ollama", False)

    if use_semantic and not _semantic_available():
        warnings.append("sentence-transformers is not installed. Continuing with RapidFuzz matching only.")
        use_semantic = False

    if use_ollama and not _ollama_available():
        warnings.append("Ollama is not reachable at localhost:11434. Reasoning notes were skipped.")
        use_ollama = False

    started = time.perf_counter()
    matches_df, candidates_by_record = match_records(
        response_df,
        gazetteer_df,
        use_semantic=use_semantic,
        use_ollama=use_ollama,
        boundary_gdf=st.session_state.get("boundary_gdf"),
    )
    st.session_state.match_df = matches_df
    st.session_state.match_candidates = candidates_by_record
    st.session_state.processing_seconds = time.perf_counter() - started
    st.session_state.processed_df = pd.DataFrame()
    st.session_state.matching_warnings = warnings
    _clear_generated_outputs()
    _bump_data_revision()


def _apply_geocodes() -> None:
    response_df = st.session_state.get("response_df")
    matches_df = st.session_state.get("match_df")
    if response_df is None or response_df.empty:
        st.warning("Load response data first.")
        return
    matches_df = normalize_review_statuses(matches_df) if matches_df is not None else pd.DataFrame()
    st.session_state.match_df = matches_df
    st.session_state.processed_df = apply_geocodes(response_df, matches_df)
    _clear_generated_outputs()
    _bump_data_revision()


def _ensure_processed() -> pd.DataFrame:
    processed_df = st.session_state.get("processed_df")
    if processed_df is not None and not processed_df.empty:
        return processed_df
    response_df = st.session_state.get("response_df")
    if response_df is None or response_df.empty:
        return pd.DataFrame()
    matches_df = st.session_state.get("match_df")
    if matches_df is None:
        matches_df = pd.DataFrame()
    processed_df = apply_geocodes(response_df, matches_df)
    st.session_state.processed_df = processed_df
    return processed_df


def _write_log(outputs: dict[str, str], elapsed: float, stage_timings: list[tuple[str, float]] | None = None) -> str:
    path = output_path("ocha_processing_log.txt")
    validation = st.session_state.get("validation_report", {})
    metrics = validation.get("metrics", {}) if validation else {}
    lines = [
        f"{APP_NAME} - Processing Log",
        f"Processing time: {elapsed:.2f} seconds",
        "",
        "Validation metrics:",
    ]
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    if stage_timings:
        lines.extend(["", "Stage timings:"])
        for label, seconds in stage_timings:
            lines.append(f"- {label}: {seconds:.2f} seconds")
    lines.extend(["", "Generated outputs:"])
    for label, output in outputs.items():
        lines.append(f"- {label}: {output}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _zip_outputs(outputs: dict[str, str]) -> str | None:
    existing = [(label, Path(path)) for label, path in outputs.items() if Path(path).exists()]
    if not existing:
        return None
    zip_path = output_path("ocha_all_outputs.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for _, path in existing:
            archive.write(path, arcname=path.name)
    return str(zip_path)


def _generate_outputs() -> None:
    processed_df = _ensure_processed()
    if processed_df.empty:
        st.warning("Load response data before generating outputs.")
        return

    selected_keys = _selected_output_keys()
    if not selected_keys:
        st.warning("Select at least one output to generate.")
        return

    validation_report = _ensure_validation()
    started = time.perf_counter()
    outputs: dict[str, str] = {}
    errors: list[str] = []
    stage_timings: list[tuple[str, float]] = []
    setup_notice = ""

    _clear_generated_outputs()
    if "QA PDF Report" in selected_keys and not _reportlab_available():
        selected_keys = set(selected_keys)
        selected_keys.remove("QA PDF Report")
        setup_notice = (
            "QA PDF Report was skipped because ReportLab is not available in the active Python "
            "environment. Run the app from .venv or install the project requirements to enable it."
        )
    if not selected_keys:
        st.session_state.output_setup_notice = setup_notice or "No runnable outputs were selected."
        return

    def run_stage(label: str, action) -> None:
        stage_started = time.perf_counter()
        try:
            outputs.update(action())
        except Exception as error:
            errors.append(f"{label}: {error}")
        finally:
            stage_timings.append((label, time.perf_counter() - stage_started))

    excel_keys = selected_keys & EXCEL_OUTPUT_KEYS
    if excel_keys:
        run_stage(
            "Excel outputs",
            lambda: export_all_excel_outputs(
                processed_df,
                st.session_state.get("match_df"),
                validation_report,
                output_keys=excel_keys,
            ),
        )

    gis_keys = selected_keys & GIS_OUTPUT_KEYS
    if gis_keys:
        run_stage("GIS outputs", lambda: export_gis_outputs(processed_df, output_keys=gis_keys))

    if "QA Excel Report" in selected_keys:
        run_stage(
            "QA Excel Report",
            lambda: {
                "QA Excel Report": str(
                    export_qa_excel_report(processed_df, st.session_state.get("match_df"), validation_report)
                )
            },
        )
    if "QA PDF Report" in selected_keys:
        run_stage(
            "QA PDF Report",
            lambda: {
                "QA PDF Report": str(
                    export_qa_pdf_report(
                        processed_df,
                        st.session_state.get("match_df"),
                        validation_report,
                        st.session_state.get("processing_seconds"),
                    )
                )
            },
        )

    audit_keys = selected_keys & AUDIT_OUTPUT_KEYS
    if audit_keys:
        def _generate_audit_outputs() -> dict[str, str]:
            conn = get_connection()
            try:
                review_decisions_df = list_review_decisions(conn)
            finally:
                conn.close()
            matches_df = st.session_state.get("match_df")
            semantic_used = bool(st.session_state.get("use_semantic", False))
            ollama_used = bool(st.session_state.get("use_ollama", False))
            result: dict[str, str] = {}
            if "Audit Log CSV" in audit_keys:
                result["Audit Log CSV"] = str(
                    export_audit_csv(matches_df, review_decisions_df, semantic_used, ollama_used)
                )
            if "Audit Log Excel" in audit_keys:
                result["Audit Log Excel"] = str(
                    export_audit_excel(matches_df, review_decisions_df, semantic_used, ollama_used)
                )
            return result

        run_stage("Audit Log", _generate_audit_outputs)

    elapsed = time.perf_counter() - started
    outputs["Log File"] = _write_log(outputs, elapsed, stage_timings)
    zip_file = _zip_outputs(outputs)
    if zip_file:
        outputs["All Outputs ZIP"] = zip_file
    st.session_state.generated_outputs = outputs
    st.session_state.output_errors = errors
    st.session_state.output_setup_notice = setup_notice
    st.session_state.output_stage_timings = stage_timings


def _metric(metrics: dict[str, Any], key: str, default: int | float = 0) -> Any:
    return metrics.get(key, default) if metrics else default


def _user_guide_href() -> str:
    guide_pdf_path = STATIC_DIR / "user_guide.pdf"
    if guide_pdf_path.exists():
        return "app/static/user_guide.pdf"
    guide_html_path = STATIC_DIR / "user_guide.html"
    if guide_html_path.exists():
        return "app/static/user_guide.html"
    return ""


def _top_header() -> None:
    mark = _file_icon()
    mark_html = f'<img src="{mark}" alt="OCHA" />' if mark else '<span>OCHA</span>'
    guide_href = _user_guide_href()
    guide_html = (
        f'<a class="about-pill" href="{_e(guide_href)}" target="_blank" rel="noopener noreferrer">User Guide</a>'
        if guide_href
        else '<span class="about-pill">User Guide</span>'
    )
    _html(
        f"""
        <div class="ocha-shell-header">
            <div class="ocha-brand">
                <div class="ocha-brand-mark">{mark_html}</div>
                <div>
                    <div class="ocha-title">{_e(APP_NAME)}</div>
                    <div class="ocha-subtitle">Geocode &bull; Summarize &bull; Map &bull; Export</div>
                </div>
            </div>
            <div class="ocha-header-actions">
                <span class="local-mode">Local Mode <span>(All data stays on this device)</span></span>
                {guide_html}
            </div>
        </div>
        """,
    )


def _workflow_stage() -> int:
    if st.session_state.get("generated_outputs"):
        return 5
    processed_df = st.session_state.get("processed_df")
    if processed_df is not None and not processed_df.empty:
        return 4
    match_df = st.session_state.get("match_df")
    if match_df is not None and not match_df.empty:
        return 3
    if st.session_state.get("validation_report"):
        return 2
    if _has_data():
        return 1
    return 0


def _workflow_item(number: int, label: str, stage: int) -> str:
    state = "done" if stage > number else "active" if stage == number else "waiting"
    marker = "OK" if state == "done" else str(number)
    return f'<div class="workflow-item {state}"><span>{marker}</span><strong>{number}. {label}</strong></div>'


def _sidebar() -> None:
    stage = _workflow_stage()
    response_df = st.session_state.get("response_df", pd.DataFrame())
    match_df = st.session_state.get("match_df", pd.DataFrame())
    processed_df = st.session_state.get("processed_df", pd.DataFrame())
    stats = matching_statistics(match_df)
    metrics = _ensure_validation().get("metrics", {}) if _has_data() else {}

    with st.sidebar:
        _html(
            f"""
            <div class="workflow-panel">
                <div class="rail-section-title">Workflow</div>
                {_workflow_item(1, "Upload Data", stage)}
                {_workflow_item(2, "Data Validation", stage)}
                {_workflow_item(3, "Settlement Matching", stage)}
                {_workflow_item(4, "Review Matches", stage)}
                {_workflow_item(5, "Generate Outputs", stage)}
                <div class="rail-divider"></div>
                <div class="rail-section-title">Reference Data</div>
                <div class="reference-row"><span>Settlement Layer</span><small>{_e(st.session_state.get("source_files", {}).get("gazetteer", "Not loaded"))}</small></div>
                <div class="reference-row"><span>District Boundaries</span><small>{_e(st.session_state.get("source_files", {}).get("boundaries", "Not loaded"))}</small></div>
                <div class="rail-divider"></div>
                <div class="rail-section-title">Information</div>
                <div class="info-row"><span>Total Records</span><strong>{len(response_df):,}</strong></div>
                <div class="info-row"><span>Records with GPS</span><strong>{_metric(metrics, "valid_gps", 0):,}</strong></div>
                <div class="info-row"><span>Missing GPS</span><strong>{_metric(metrics, "missing_gps", 0):,}</strong></div>
                <div class="info-row"><span>Matched</span><strong>{stats["matched"]:,}</strong></div>
                <div class="info-row"><span>Needs Review</span><strong>{stats["needs_review"]:,}</strong></div>
                <div class="info-row"><span>Processed</span><strong>{len(processed_df):,}</strong></div>
            </div>
            """,
        )

        if st.button("Load Sample Data", use_container_width=True, key="load_sample"):
            _load_sample()
            st.rerun()

        with st.expander("Upload files", expanded=not _has_data()):
            response_upload = st.file_uploader("Response Excel or CSV", type=["xlsx", "xls", "csv"])
            gazetteer_upload = st.file_uploader(
                "Settlement Gazetteer",
                type=["xlsx", "xls", "csv", "geojson", "json", "gpkg", "zip"],
            )
            boundary_upload = st.file_uploader("District Boundary Layer", type=["geojson", "json", "gpkg", "zip"])
            if st.button("Load Uploaded Files", use_container_width=True):
                if response_upload is None or gazetteer_upload is None:
                    st.warning("Upload both response data and a gazetteer.")
                else:
                    try:
                        _load_uploaded(response_upload, gazetteer_upload, boundary_upload)
                        st.rerun()
                    except DataLoadError as error:
                        st.error(str(error))
                    except Exception as error:
                        st.error(f"Could not load files: {error}")

        if st.button("Run Matching", use_container_width=True, disabled=not _has_data()):
            _run_matching()
            st.rerun()
        if st.button("Apply Geocodes", use_container_width=True, disabled=st.session_state.get("match_df", pd.DataFrame()).empty):
            _apply_geocodes()
            st.rerun()
        if st.button("Generate Outputs", use_container_width=True, disabled=not _has_data()):
            _generate_outputs()
            st.rerun()
        if st.button("Restart Process", use_container_width=True):
            _reset_workflow()
            st.rerun()


def _uploaded_file_card(title: str, name: str, detail: str, tone: str) -> str:
    return f"""
    <div class="uploaded-card">
        <div class="file-glyph {tone}">{title[:1]}</div>
        <div>
            <strong>{_e(title)}</strong>
            <span>{_e(name)}</span>
            <small>{_e(detail)}</small>
        </div>
    </div>
    """


def _uploaded_files_panel(metrics: dict[str, Any]) -> None:
    source_files = st.session_state.get("source_files", {})
    response_rows = len(st.session_state.get("response_df", pd.DataFrame()))
    gazetteer_rows = len(st.session_state.get("gazetteer_df", pd.DataFrame()))
    boundary_rows = _metric(metrics, "boundary_features", 0)
    _html(
        f"""
        <div class="panel-card">
            <div class="section-title">Uploaded Files</div>
            <div class="uploaded-grid">
                {_uploaded_file_card("Response Data", source_files.get("response", "Awaiting file"), f"{response_rows:,} rows", "green")}
                {_uploaded_file_card("Settlement / Village Layer", source_files.get("gazetteer", "Awaiting file"), f"{gazetteer_rows:,} settlements", "blue")}
                {_uploaded_file_card("District Boundaries", source_files.get("boundaries", "Optional"), f"{boundary_rows:,} districts", "navy")}
            </div>
        </div>
        """,
    )


def _process_panel() -> None:
    stage = _workflow_stage()
    steps = [("Upload", 1), ("Validate", 2), ("Match", 3), ("Review", 4), ("Outputs", 5)]
    step_html = []
    for label, number in steps:
        state = "done" if stage > number else "active" if stage == number else "waiting"
        marker = "OK" if state == "done" else str(number)
        step_html.append(
            f'<div class="process-step {state}"><span>{marker}</span><strong>{_e(label)}</strong></div>'
        )
    _html(
        f"""
        <div class="panel-card process-card">
            <div class="section-title">Process Overview</div>
            <div class="process-line">{"".join(step_html)}</div>
        </div>
        """,
    )


def _summary_card(label: str, value: str, detail: str, tone: str) -> str:
    return f"""
    <div class="summary-card {tone}">
        <div>
            <span>{_e(label)}</span>
            <strong>{_e(value)}</strong>
            <small>{_e(detail)}</small>
        </div>
        <em>{_e(label[:1])}</em>
    </div>
    """


def _validation_summary(metrics: dict[str, Any]) -> None:
    total = int(_metric(metrics, "total_records", 0))
    valid = int(_metric(metrics, "valid_gps", 0))
    missing = int(_metric(metrics, "missing_gps", 0))
    duplicates = int(_metric(metrics, "duplicate_records", 0))
    invalid = int(_metric(metrics, "invalid_coordinates", 0))
    missing_names = int(_metric(metrics, "missing_settlements", 0))
    _html(
        f"""
        <div class="section-title">Data Validation Summary</div>
        <div class="summary-grid">
            {_summary_card("Total Records", f"{total:,}", "Loaded response rows", "blue")}
            {_summary_card("With Coordinates", f"{valid:,}", f"{safe_percent(valid, total)}%", "green")}
            {_summary_card("Missing Coordinates", f"{missing:,}", f"{safe_percent(missing, total)}%", "orange")}
            {_summary_card("Duplicates", f"{duplicates:,}", f"{safe_percent(duplicates, total)}%", "purple")}
            {_summary_card("Invalid Coordinates", f"{invalid:,}", f"{safe_percent(invalid, total)}%", "red")}
            {_summary_card("Missing Settlement Name", f"{missing_names:,}", f"{safe_percent(missing_names, total)}%", "slate")}
        </div>
        """,
    )


def _status_class(status: str) -> str:
    status = status.lower()
    if status in {"auto_accepted", "accepted", "manual_accepted"}:
        return "accept"
    if status == "needs_review":
        return "review"
    return "reject"


def _ai_status_item(title: str, detail: str, ready: bool, required: bool = False) -> str:
    state = "ready" if ready else "blocked" if required else "optional"
    label = "Ready" if ready else "Missing" if required else "Optional"
    return f"""
    <div class="ai-status-item {state}">
        <div>
            <strong>{_e(title)}</strong>
            <span>{_e(detail)}</span>
        </div>
        <em>{_e(label)}</em>
    </div>
    """


def _ai_readiness_panel(semantic_ready: bool, ollama_ready: bool) -> None:
    _html(
        f"""
        <div class="ai-readiness">
            {_ai_status_item("RapidFuzz matcher", "Core fuzzy settlement matching engine", _rapidfuzz_available(), required=True)}
            {_ai_status_item("Sentence Transformers", "Local semantic matching for spelling and wording variants", semantic_ready)}
            {_ai_status_item("Ollama qwen2.5", "Local reasoning notes for low-confidence review cases", ollama_ready)}
        </div>
        """,
    )


def _prune_matching_warnings(semantic_ready: bool, ollama_ready: bool) -> None:
    warnings = st.session_state.get("matching_warnings", [])
    if not warnings:
        return
    use_semantic = st.session_state.get("use_semantic", False)
    use_ollama = st.session_state.get("use_ollama", False)
    cleaned: list[str] = []
    for warning in warnings:
        lowered = warning.lower()
        if "sentence-transformers" in lowered and (semantic_ready or not use_semantic):
            continue
        if "ollama" in lowered and (ollama_ready or not use_ollama):
            continue
        cleaned.append(warning)
    st.session_state.matching_warnings = cleaned


def _matching_table(matches_df: pd.DataFrame) -> str:
    if matches_df is None or matches_df.empty:
        return '<div class="empty-panel">Run matching to populate settlement suggestions.</div>'

    rows = []
    for _, row in matches_df.head(8).iterrows():
        status = str(row.get("status", "unresolved"))
        confidence = row.get("confidence", 0)
        rows.append(
            f"""
            <tr>
                <td>{_e(row.get("submitted_settlement", ""))}</td>
                <td>{_e(row.get("submitted_district", ""))}</td>
                <td>{_e(row.get("suggested_settlement", ""))}</td>
                <td><span class="confidence {_status_class(status)}">{_e(confidence)}%</span></td>
                <td>{_e(row.get("latitude", ""))}</td>
                <td>{_e(row.get("longitude", ""))}</td>
                <td><span class="action-pill {_status_class(status)}">{'Accept' if _status_class(status) == 'accept' else 'Review'}</span></td>
            </tr>
            """
        )
    return f"""
    <div class="match-table-wrap">
        <table class="match-table">
            <thead>
                <tr>
                    <th>Submitted Settlement</th>
                    <th>Submitted District</th>
                    <th>Suggested Match</th>
                    <th>Confidence</th>
                    <th>Lat</th>
                    <th>Lon</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </div>
    """


def _merge_reviewed_matches(matches_df: pd.DataFrame, edited_subset: pd.DataFrame) -> pd.DataFrame:
    if edited_subset.empty:
        return matches_df
    merged = matches_df.set_index("record_id")
    edits = edited_subset.set_index("record_id")
    for column in edits.columns:
        merged.loc[edits.index, column] = edits[column]
    return merged.reset_index()


def _review_queue_editor(matches_df: pd.DataFrame) -> pd.DataFrame:
    if matches_df.empty:
        return matches_df
    status_lower = matches_df["status"].astype(str).str.lower()
    review_subset = matches_df.loc[status_lower.isin({"needs_review", "unresolved"})].copy()
    if review_subset.empty:
        st.caption("No matches currently need review.")
        return matches_df

    st.markdown(f"**Needs Review Queue** — {len(review_subset):,} matches awaiting a decision")
    st.caption(
        "Accept the suggested match, reject it, or correct the settlement, district, "
        "or coordinates directly, then click Save Reviewed Matches below."
    )
    display_columns = [
        "record_id",
        "submitted_settlement",
        "submitted_district",
        "suggested_settlement",
        "suggested_district",
        "confidence",
        "latitude",
        "longitude",
        "status",
        "accept",
        "reject",
    ]
    edited_subset = st.data_editor(
        review_subset[display_columns],
        column_config={
            "record_id": st.column_config.NumberColumn("Row ID", disabled=True),
            "submitted_settlement": st.column_config.TextColumn("Submitted Settlement", disabled=True),
            "submitted_district": st.column_config.TextColumn("Submitted District", disabled=True),
            "suggested_settlement": st.column_config.TextColumn("Suggested Settlement"),
            "suggested_district": st.column_config.TextColumn("Suggested District"),
            "confidence": st.column_config.NumberColumn("Confidence %", disabled=True, format="%.1f"),
            "latitude": st.column_config.NumberColumn("Latitude", format="%.6f"),
            "longitude": st.column_config.NumberColumn("Longitude", format="%.6f"),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["needs_review", "accepted", "rejected", "unresolved", "manual_accepted"],
            ),
            "accept": st.column_config.CheckboxColumn("Accept"),
            "reject": st.column_config.CheckboxColumn("Reject"),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key="needs_review_editor",
    )
    return _merge_reviewed_matches(matches_df, edited_subset)


def apply_candidate_selection(
    matches_df: pd.DataFrame, record_id: int, chosen_candidate: dict[str, object]
) -> pd.DataFrame:
    """Overwrite a match row's suggestion with a manually-selected alternate candidate.

    Marks the row accepted (matching_method "manual_selection") so the
    analyst's explicit choice - not the pipeline's original top pick - is
    what gets written to processed_df and taught back to the alias table
    when they save.
    """
    matches_df = matches_df.copy()
    idx = matches_df.index[matches_df["record_id"] == record_id][0]
    matches_df.loc[idx, "suggested_settlement"] = chosen_candidate["settlement"]
    matches_df.loc[idx, "suggested_district"] = chosen_candidate["district"]
    matches_df.loc[idx, "suggested_region"] = chosen_candidate["region"]
    matches_df.loc[idx, "latitude"] = chosen_candidate["latitude"]
    matches_df.loc[idx, "longitude"] = chosen_candidate["longitude"]
    matches_df.loc[idx, "suggested_gazetteer_id"] = chosen_candidate["gazetteer_id"]
    matches_df.loc[idx, "official_district"] = chosen_candidate["district"]
    matches_df.loc[idx, "official_region"] = chosen_candidate["region"]
    matches_df.loc[idx, "official_latitude"] = chosen_candidate["latitude"]
    matches_df.loc[idx, "official_longitude"] = chosen_candidate["longitude"]
    matches_df.loc[idx, "confidence"] = chosen_candidate["overall_confidence"]
    matches_df.loc[idx, "overall_confidence"] = chosen_candidate["overall_confidence"]
    matches_df.loc[idx, "matching_method"] = "manual_selection"
    matches_df.loc[idx, "candidate_rank"] = chosen_candidate["rank"]
    matches_df.loc[idx, "accept"] = True
    matches_df.loc[idx, "reject"] = False
    matches_df.loc[idx, "status"] = "accepted"
    matches_df.loc[idx, "decision_status"] = "accepted"
    return matches_df


def _candidate_comparison_panel(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Let a reviewer inspect the full ranked candidate shortlist for a record
    (not just the single top suggestion) and pick a different one if it's wrong."""
    candidates_by_record = st.session_state.get("match_candidates", {})
    if matches_df.empty or not candidates_by_record:
        return matches_df

    status_lower = matches_df["status"].astype(str).str.lower()
    review_subset = matches_df.loc[status_lower.isin({"needs_review", "unresolved"})]
    reviewable_ids = [rid for rid in review_subset["record_id"].tolist() if rid in candidates_by_record]
    if not reviewable_ids:
        return matches_df

    st.markdown("**Compare Candidates**")
    st.caption(
        "Inspect the top alternatives the pipeline considered for a specific record, "
        "and select a different one if the top suggestion looks wrong."
    )

    def _record_label(record_id: int) -> str:
        submitted = matches_df.loc[matches_df["record_id"] == record_id, "submitted_settlement"].iloc[0]
        return f"Row {record_id}: {submitted}"

    selected_id = st.selectbox(
        "Record to compare",
        options=reviewable_ids,
        format_func=_record_label,
        key="candidate_comparison_record",
    )

    candidates = candidates_by_record.get(selected_id, [])
    if not candidates:
        st.caption("No alternative candidates were found for this record.")
        return matches_df

    comparison_df = pd.DataFrame(candidates)
    display_columns = {
        "rank": "Rank",
        "settlement": "Settlement",
        "district": "District",
        "region": "Region",
        "name_score": "Name %",
        "semantic_score": "Semantic %",
        "spatial_score": "Spatial %",
        "historical_score": "Historical %",
        "distance_km": "Distance (km)",
        "overall_confidence": "Confidence %",
        "admin_conflict": "Admin Conflict",
    }
    available_columns = [column for column in display_columns if column in comparison_df.columns]
    st.dataframe(
        comparison_df[available_columns].rename(columns=display_columns),
        use_container_width=True,
        hide_index=True,
    )

    candidate_by_rank = {candidate["rank"]: candidate for candidate in candidates}

    def _candidate_label(rank: int) -> str:
        candidate = candidate_by_rank[rank]
        district = candidate["district"] or "unknown district"
        return f"#{rank}: {candidate['settlement']} ({district})"

    chosen_rank = st.selectbox(
        "Select a candidate to use instead",
        options=list(candidate_by_rank.keys()),
        format_func=_candidate_label,
        key="candidate_comparison_choice",
    )

    if st.button("Use This Candidate", key="use_candidate_button"):
        chosen = candidate_by_rank[chosen_rank]
        matches_df = apply_candidate_selection(matches_df, selected_id, chosen)
        st.session_state.match_df = matches_df
        st.success(f"Row {selected_id} updated to use candidate #{chosen_rank}: {chosen['settlement']}.")
        st.rerun()

    return matches_df


def _matching_panel() -> None:
    matches_df = st.session_state.get("match_df", pd.DataFrame())
    stats = matching_statistics(matches_df)
    semantic_ready = _semantic_available()
    ollama_ready = _ollama_available(timeout=0.6)
    if not semantic_ready:
        st.session_state.use_semantic = False
    if not ollama_ready:
        st.session_state.use_ollama = False
    ai_enabled = st.session_state.get("use_semantic", False) or st.session_state.get("use_ollama", False)
    ai_label = " <span>(AI Enabled)</span>" if ai_enabled else ""
    _html(
        f"""
        <div class="panel-card panel-fill">
            <div class="section-title">Settlement Matching{ai_label}</div>
            {_matching_table(matches_df)}
            <div class="match-legend">
                <span><i class="dot green"></i> Auto Matched ({stats["auto_accepted"]:,})</span>
                <span><i class="dot orange"></i> Needs Review ({stats["needs_review"]:,})</span>
                <span><i class="dot red"></i> Unmatched ({stats["unresolved"]:,})</span>
                <span><i class="dot gray"></i> Manually Edited</span>
            </div>
        </div>
        """,
    )

    _ai_readiness_panel(semantic_ready, ollama_ready)

    st.checkbox(
        "Enable semantic matching with Sentence Transformers",
        key="use_semantic",
        disabled=not semantic_ready,
        help="Uses the local all-MiniLM-L6-v2 embedding model when the package is available.",
    )
    st.caption(
        "Improves settlement matching using local text embeddings. "
        "Install requirements or run the project virtual environment if this is unavailable."
    )
    if st.session_state.get("use_semantic"):
        st.info("Semantic matching enabled.")

    st.checkbox(
        "Enable Ollama reasoning notes",
        key="use_ollama",
        disabled=not ollama_ready,
        help="Requires a local Ollama server with qwen2.5 available at localhost:11434.",
    )
    st.caption("Adds short local AI reasoning notes for low-confidence matches. Start Ollama locally to enable it.")
    if st.session_state.get("use_ollama"):
        st.info("Ollama reasoning enabled. Make sure Ollama is running with qwen2.5.")

    _prune_matching_warnings(semantic_ready, ollama_ready)
    for warning_message in st.session_state.get("matching_warnings", []):
        st.warning(warning_message)

    matches_df = _review_queue_editor(matches_df)
    matches_df = _candidate_comparison_panel(matches_df)
    st.session_state.match_df = matches_df

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Run Settlement Matching", use_container_width=True, disabled=not _has_data()):
            _run_matching()
            st.rerun()
    with c2:
        if st.button("Save Reviewed Matches", type="primary", use_container_width=True, disabled=matches_df.empty):
            st.session_state.match_df = normalize_review_statuses(matches_df)
            _apply_geocodes()
            st.rerun()


def _map_metric_items(processed_df: pd.DataFrame) -> str:
    columns = detect_column_map(processed_df)
    lat_col = columns.get("latitude")
    lon_col = columns.get("longitude")
    district_col = columns.get("district")
    valid_points = 0
    if lat_col and lon_col:
        lat = pd.to_numeric(processed_df[lat_col], errors="coerce")
        lon = pd.to_numeric(processed_df[lon_col], errors="coerce")
        valid_points = int((lat.between(-90, 90) & lon.between(-180, 180)).sum())
    district_count = int(processed_df[district_col].dropna().nunique()) if district_col else 0
    boundary_gdf = st.session_state.get("boundary_gdf")
    boundary_count = int(len(boundary_gdf)) if boundary_gdf is not None else 0
    return f"""
    <div class="map-stat-grid">
        <div class="map-stat"><span>Mapped Records</span><strong>{valid_points:,}</strong></div>
        <div class="map-stat"><span>Districts</span><strong>{district_count:,}</strong></div>
        <div class="map-stat"><span>Boundary Features</span><strong>{boundary_count:,}</strong></div>
    </div>
    """


def _response_map_html(processed_df: pd.DataFrame) -> str:
    boundary_gdf = st.session_state.get("boundary_gdf")
    matches_df = st.session_state.get("match_df")
    boundary_count = int(len(boundary_gdf)) if boundary_gdf is not None else 0
    match_count = len(matches_df) if matches_df is not None else 0
    cache_key = (
        st.session_state.get("data_revision", 0),
        len(processed_df),
        len(processed_df.columns),
        boundary_count,
        match_count,
    )
    cache = st.session_state.setdefault("map_cache", {})
    if cache.get("key") == cache_key:
        return cache["html"]

    response_map = create_response_map(processed_df, boundary_gdf, matches_df)
    html_output = response_map._repr_html_()
    st.session_state.map_cache = {"key": cache_key, "html": html_output}
    return html_output


_MAP_STATUS_ORDER = [
    "auto_accepted",
    "accepted",
    "manual_accepted",
    "needs_review",
    "unresolved",
    "rejected",
    "already_geocoded",
]


def _map_legend_items(processed_df: pd.DataFrame, matches_df: pd.DataFrame | None) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    if "Match Status" in processed_df.columns:
        for status in processed_df["Match Status"].dropna().astype(str).str.lower().unique():
            seen.setdefault(status, STATUS_COLORS.get(status, "#0078D4"))
    if matches_df is not None and not matches_df.empty and "status" in matches_df.columns:
        review_statuses = {"needs_review", "unresolved", "rejected"}
        for status in matches_df["status"].dropna().astype(str).str.lower().unique():
            if status in review_statuses:
                seen.setdefault(status, STATUS_COLORS.get(status, "#FFB900"))
    ordered_statuses = sorted(
        seen,
        key=lambda status: _MAP_STATUS_ORDER.index(status) if status in _MAP_STATUS_ORDER else len(_MAP_STATUS_ORDER),
    )
    return [(status.replace("_", " ").title(), seen[status]) for status in ordered_statuses]


def _map_has_flagged_conflict(matches_df: pd.DataFrame | None) -> bool:
    if matches_df is None or matches_df.empty:
        return False
    district_score = pd.to_numeric(matches_df.get("district_score"), errors="coerce")
    region_score = pd.to_numeric(matches_df.get("region_score"), errors="coerce")
    distance_km = pd.to_numeric(matches_df.get("distance_km"), errors="coerce")
    admin_conflict = (district_score < ADMIN_CONTRADICTION_THRESHOLD) | (region_score < ADMIN_CONTRADICTION_THRESHOLD)
    spatial_conflict = distance_km > MAX_AUTO_ACCEPT_DISTANCE_KM
    return bool((admin_conflict.fillna(False) | spatial_conflict.fillna(False)).any())


def _map_legend_html(processed_df: pd.DataFrame, matches_df: pd.DataFrame | None) -> str:
    items = _map_legend_items(processed_df, matches_df)
    if not items:
        return ""
    swatches = "".join(
        f'<span><i class="dot" style="background:{color};"></i>{_e(label)}</span>' for label, color in items
    )
    conflict_note = (
        '<span><i class="dot" style="background:transparent;border:2px dashed #667085;"></i>'
        "Dashed ring = administrative or spatial conflict flagged</span>"
        if _map_has_flagged_conflict(matches_df)
        else ""
    )
    return f'<div class="map-legend">{swatches}{conflict_note}</div>'


def _map_panel() -> None:
    processed_df = _ensure_processed()
    if processed_df.empty:
        _html(
            """
            <div class="panel-card panel-fill">
                <div class="section-title">Settlements Preview Map</div>
                <div class="empty-map">Load data to preview mapped settlements.</div>
            </div>
            """,
        )
        return

    matches_df = st.session_state.get("match_df")
    _html('<div class="section-title outside-title">Settlements Preview Map</div>')
    legend_html = _map_legend_html(processed_df, matches_df)
    if legend_html:
        _html(legend_html)
    _html(_map_metric_items(processed_df))
    try:
        response_map = create_response_map(
            processed_df,
            st.session_state.get("boundary_gdf"),
            matches_df,
        )
        try:
            from streamlit_folium import st_folium

            st_folium(
                response_map,
                use_container_width=True,
                height=DASHBOARD_MAP_HEIGHT,
                returned_objects=[],
            )
        except ImportError:
            components.html(_response_map_html(processed_df), height=DASHBOARD_MAP_HEIGHT + 20, scrolling=False)
    except Exception as error:
        st.warning(f"Map preview is unavailable: {error}")


def _output_row(title: str, output_key: str, detail: str, outputs: dict[str, str]) -> str:
    available = output_key in outputs and Path(outputs[output_key]).exists()
    blocked = output_key == "QA PDF Report" and not _reportlab_available() and not available
    state = "ready" if available else "blocked" if blocked else "pending"
    status_label = "Ready" if available else "Setup" if blocked else "Pending"
    detail_text = "ReportLab missing in active Python environment" if blocked else detail
    return f"""
    <div class="output-card {state}">
        <div class="output-icon">{_e(title[:1])}</div>
        <div>
            <strong>{_e(title)}</strong>
            <span>{_e(detail_text)}</span>
        </div>
        <em>{_e(status_label)}</em>
    </div>
    """


def _outputs_panel() -> None:
    outputs = st.session_state.get("generated_outputs", {})
    errors = st.session_state.get("output_errors", [])
    setup_notice = st.session_state.get("output_setup_notice", "")
    rows = [_output_row(title, key, detail, outputs) for title, key, detail in OUTPUT_ITEMS]
    _html(
        f"""
        <div class="panel-card panel-fill">
            <div class="section-title">Outputs Preview</div>
            <div class="output-list">{''.join(rows)}</div>
        </div>
        """,
    )
    if setup_notice:
        st.warning(setup_notice)
    for error in errors:
        st.error(error)

    st.multiselect(
        "Outputs to generate",
        options=OUTPUT_TITLES,
        key="selected_output_titles",
        disabled=not _has_data(),
    )
    selected_count = len(_selected_output_keys())
    button_label = "Generate All Outputs" if selected_count == len(OUTPUT_ITEMS) else "Generate Selected Outputs"
    if st.button(button_label, use_container_width=True, type="primary", disabled=not _has_data()):
        _generate_outputs()
        st.rerun()

    stage_timings = st.session_state.get("output_stage_timings", [])
    if stage_timings:
        st.caption(" | ".join(f"{label}: {seconds:.2f}s" for label, seconds in stage_timings))

    zip_path = outputs.get("All Outputs ZIP")
    if zip_path and Path(zip_path).exists():
        file_path = Path(zip_path)
        st.download_button(
            "Download All Outputs",
            data=_download_bytes(file_path),
            file_name=file_path.name,
            mime="application/zip",
            use_container_width=True,
        )

    with st.expander("Individual files", expanded=False):
        for label, path in outputs.items():
            file_path = Path(path)
            if not file_path.exists() or label == "All Outputs ZIP":
                continue
            st.download_button(
                f"Download {label}",
                data=_download_bytes(file_path),
                file_name=file_path.name,
                mime="application/octet-stream",
                use_container_width=True,
                key=f"download_{label}_{file_path.name}",
            )


def _local_notice() -> None:
    _html(
        """
        <div class="local-notice">
            <strong>Local processing:</strong> all data stays on this device.
        </div>
        """,
    )


def render() -> None:
    _state_defaults()
    _top_header()
    _sidebar()

    validation_report = _ensure_validation() if _has_data() else {}
    metrics = validation_report.get("metrics", {}) if validation_report else {}

    top_left, top_right = st.columns([1.65, 1], gap="small")
    with top_left:
        _uploaded_files_panel(metrics)
    with top_right:
        _process_panel()

    _validation_summary(metrics)

    match_col, output_col = st.columns([1.6, 1], gap="small")
    with match_col:
        _matching_panel()
    with output_col:
        _outputs_panel()

    _map_panel()

    _local_notice()
