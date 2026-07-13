from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from backend.district_summary import build_summary_tables
from backend.utils import output_path
from config import APP_NAME


QA_OUTPUT_KEYS = {"QA Excel Report", "QA PDF Report"}


def _selected_keys(output_keys: Iterable[str] | None) -> set[str]:
    return set(output_keys) if output_keys is not None else set(QA_OUTPUT_KEYS)


def export_qa_excel_report(
    processed_df: pd.DataFrame,
    matches_df: pd.DataFrame | None,
    validation_report: dict[str, object] | None,
) -> Path:
    path = output_path("settlement_qa_report.xlsx")
    metrics = validation_report.get("metrics", {}) if validation_report else {}
    issues = validation_report.get("issues", []) if validation_report else []
    summary_tables = build_summary_tables(processed_df)

    from backend.excel_exporter import _excel_writer, _is_xlsxwriter, _style_workbook, _write_dataframe

    with _excel_writer(path) as writer:
        _write_dataframe(
            writer,
            pd.DataFrame(
                [{"Metric": key.replace("_", " ").title(), "Value": value} for key, value in metrics.items()]
            ),
            "Readiness Metrics",
        )
        _write_dataframe(writer, pd.DataFrame(issues), "QA Issues")
        if matches_df is not None and not matches_df.empty:
            _write_dataframe(writer, matches_df, "Settlement Matches")
            _write_dataframe(
                writer,
                matches_df[matches_df["status"].isin(["needs_review", "unresolved"])],
                "Low Confidence",
            )
        _write_dataframe(writer, summary_tables["district_summary"], "District Summary")
        _write_dataframe(writer, summary_tables["cluster_summary"], "Cluster Summary")
        if not _is_xlsxwriter(writer):
            _style_workbook(writer.book)
    return path


def export_qa_pdf_report(
    processed_df: pd.DataFrame,
    matches_df: pd.DataFrame | None,
    validation_report: dict[str, object] | None,
    processing_seconds: float | None = None,
) -> Path:
    path = output_path("settlement_qa_report.pdf")
    metrics = validation_report.get("metrics", {}) if validation_report else {}
    issues = validation_report.get("issues", []) if validation_report else []

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as error:
        raise RuntimeError("ReportLab is required to generate the PDF QA report.") from error

    document = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=32, leftMargin=32, topMargin=32, bottomMargin=32)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(APP_NAME, styles["Title"]),
        Paragraph("Quality Assurance Report", styles["Heading2"]),
        Spacer(1, 12),
    ]

    if processing_seconds is not None:
        elements.append(Paragraph(f"Processing time: {processing_seconds:.2f} seconds", styles["Normal"]))
        elements.append(Spacer(1, 8))

    metric_rows = [["Metric", "Value"]]
    for key, value in metrics.items():
        metric_rows.append([key.replace("_", " ").title(), str(value)])
    metric_table = Table(metric_rows, hAlign="LEFT", colWidths=[230, 220])
    metric_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8C6C4")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F8FC")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(metric_table)
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("Key QA Issues", styles["Heading2"]))
    if issues:
        issue_rows = [["Severity", "Issue", "Count", "Details"]]
        for issue in issues[:18]:
            issue_rows.append(
                [
                    str(issue.get("severity", "")).title(),
                    str(issue.get("title", "")),
                    str(issue.get("count", "")),
                    str(issue.get("details", ""))[:90],
                ]
            )
        issue_table = Table(issue_rows, hAlign="LEFT", colWidths=[70, 140, 50, 210])
        issue_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8C6C4")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(issue_table)
    else:
        elements.append(Paragraph("No major QA issues detected.", styles["Normal"]))

    elements.append(Spacer(1, 14))
    if matches_df is not None and not matches_df.empty:
        status_counts = matches_df["status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Records"]
        rows = [["Status", "Records"]] + status_counts.astype(str).values.tolist()
        table = Table(rows, hAlign="LEFT", colWidths=[220, 120])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8C6C4")),
                ]
            )
        )
        elements.append(Paragraph("Settlement Matching Accuracy", styles["Heading2"]))
        elements.append(table)

    document.build(elements)
    return path


def export_qa_reports(
    processed_df: pd.DataFrame,
    matches_df: pd.DataFrame | None,
    validation_report: dict[str, object] | None,
    processing_seconds: float | None = None,
    output_keys: Iterable[str] | None = None,
) -> dict[str, str]:
    selected = _selected_keys(output_keys)
    outputs: dict[str, str] = {}
    if "QA Excel Report" in selected:
        outputs["QA Excel Report"] = str(export_qa_excel_report(processed_df, matches_df, validation_report))
    if "QA PDF Report" in selected:
        outputs["QA PDF Report"] = str(
            export_qa_pdf_report(processed_df, matches_df, validation_report, processing_seconds)
        )
    return outputs
