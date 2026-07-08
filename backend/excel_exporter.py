from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.district_summary import build_summary_tables, district_groups
from backend.utils import output_path, truncate_sheet_name
from config import CLUSTER_COLORS


HEADER_FILL = "1F4E79"
HEADER_FONT = "FFFFFF"
LIGHT_FILL = "D9EAF7"


def _validation_frames(validation_report: dict[str, object] | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not validation_report:
        return pd.DataFrame(), pd.DataFrame()
    metrics = validation_report.get("metrics", {})
    metric_df = pd.DataFrame(
        [{"Metric": key.replace("_", " ").title(), "Value": value} for key, value in metrics.items()]
    )
    issues_df = pd.DataFrame(validation_report.get("issues", []))
    return metric_df, issues_df


def _style_workbook(path: Path) -> None:
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = load_workbook(path)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL)
    header_font = Font(color=HEADER_FONT, bold=True)
    light_fill = PatternFill("solid", fgColor=LIGHT_FILL)

    for worksheet in workbook.worksheets:
        worksheet.freeze_panes = "A2"
        worksheet.sheet_view.showGridLines = False
        if worksheet.max_row >= 1:
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 42)
        if worksheet.title == "Summary":
            for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
                if row[0].row % 2 == 0:
                    for cell in row:
                        cell.fill = light_fill

    workbook.save(path)


def export_cleaned_excel(
    processed_df: pd.DataFrame,
    matches_df: pd.DataFrame | None = None,
    validation_report: dict[str, object] | None = None,
) -> Path:
    path = output_path("ocha_cleaned_response.xlsx")
    metric_df, issues_df = _validation_frames(validation_report)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        processed_df.to_excel(writer, sheet_name="Cleaned Response", index=False)
        if matches_df is not None and not matches_df.empty:
            matches_df.to_excel(writer, sheet_name="Settlement Matches", index=False)
        if not metric_df.empty:
            metric_df.to_excel(writer, sheet_name="Validation Metrics", index=False)
        if not issues_df.empty:
            issues_df.to_excel(writer, sheet_name="Validation Issues", index=False)
    _style_workbook(path)
    return path


def export_district_workbook(processed_df: pd.DataFrame) -> Path:
    path = output_path("ocha_district_response_workbook.xlsx")
    summary_tables = build_summary_tables(processed_df)
    _, groups = district_groups(processed_df)
    used_sheet_names: set[str] = set()

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary_tables["district_summary"].to_excel(writer, sheet_name="Summary", index=False)
        summary_tables["cluster_summary"].to_excel(writer, sheet_name="Cluster Summary", index=False)
        summary_tables["partner_summary"].to_excel(writer, sheet_name="Partner Summary", index=False)

        for district, group in groups:
            sheet_name = truncate_sheet_name(district, used_sheet_names)
            group.to_excel(writer, sheet_name=sheet_name, index=False)

    _enhance_district_workbook(path)
    return path


def export_district_summary(processed_df: pd.DataFrame) -> Path:
    path = output_path("ocha_district_summary.xlsx")
    summary_tables = build_summary_tables(processed_df)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary_tables["district_summary"].to_excel(writer, sheet_name="District Summary", index=False)
        summary_tables["cluster_summary"].to_excel(writer, sheet_name="Cluster Summary", index=False)
        summary_tables["partner_summary"].to_excel(writer, sheet_name="Partner Summary", index=False)
    _style_workbook(path)
    return path


def _enhance_district_workbook(path: Path) -> None:
    from openpyxl import load_workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Font, PatternFill

    _style_workbook(path)
    workbook = load_workbook(path)

    if "Summary" in workbook.sheetnames:
        ws = workbook["Summary"]
        if ws.max_row > 1 and ws.max_column >= 5:
            chart = BarChart()
            chart.title = "Beneficiaries by District"
            chart.y_axis.title = "Beneficiaries"
            chart.x_axis.title = "District"
            data = Reference(ws, min_col=5, min_row=1, max_row=ws.max_row)
            categories = Reference(ws, min_col=1, min_row=2, max_row=ws.max_row)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(categories)
            chart.height = 8
            chart.width = 18
            ws.add_chart(chart, "H2")

    if "Cluster Summary" in workbook.sheetnames:
        ws = workbook["Cluster Summary"]
        cluster_col = None
        for idx, cell in enumerate(ws[1], start=1):
            if str(cell.value).strip().lower() == "cluster":
                cluster_col = idx
                break
        if cluster_col:
            for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                cluster = str(row[cluster_col - 1].value or "").strip().lower()
                fill_color = CLUSTER_COLORS.get(cluster)
                if fill_color:
                    for cell in row:
                        cell.fill = PatternFill("solid", fgColor=fill_color)
                        cell.font = Font(color="000000")

    workbook.save(path)


def export_all_excel_outputs(
    processed_df: pd.DataFrame,
    matches_df: pd.DataFrame | None,
    validation_report: dict[str, object] | None,
) -> dict[str, str]:
    cleaned_path = export_cleaned_excel(processed_df, matches_df, validation_report)
    district_path = export_district_workbook(processed_df)
    district_summary_path = export_district_summary(processed_df)
    return {
        "Cleaned Excel": str(cleaned_path),
        "District Workbook": str(district_path),
        "District Summary": str(district_summary_path),
    }
