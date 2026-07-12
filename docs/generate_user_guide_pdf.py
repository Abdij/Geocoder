"""Builds the User Guide PDF from source content and screenshots.

Run this after the app's workflow, columns, or screenshots change:

    .venv/Scripts/python docs/generate_user_guide_pdf.py

Output: static/user_guide.html's PDF counterpart at static/user_guide.pdf,
the file the header's "User Guide" button links to.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BASE_DIR / "docs" / "images"
OUT_PATH = BASE_DIR / "static" / "user_guide.pdf"

NAVY = colors.HexColor("#1F4E79")
NAVY_DARK = colors.HexColor("#122E47")
INK = colors.HexColor("#1B2430")
SOFT = colors.HexColor("#48566E")
GRID = colors.HexColor("#C8C6C4")
ROW_ALT = colors.HexColor("#F3F8FC")
GREEN = colors.HexColor("#107C10")
GREEN_SOFT = colors.HexColor("#E6F4E6")
AMBER = colors.HexColor("#9A6700")
AMBER_SOFT = colors.HexColor("#FFF4D9")
RED = colors.HexColor("#C50F1F")
RED_SOFT = colors.HexColor("#FCE8E9")
GREY = colors.HexColor("#605E5C")
GREY_SOFT = colors.HexColor("#EEEEED")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 2.2 * cm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("CoverTitle", parent=styles["Title"], fontSize=26, leading=30, textColor=NAVY, spaceAfter=6))
styles.add(ParagraphStyle("CoverSubtitle", parent=styles["Heading2"], fontSize=15, textColor=INK, spaceAfter=4))
styles.add(ParagraphStyle("CoverByline", parent=styles["Normal"], fontSize=11, textColor=SOFT, spaceAfter=2))
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, textColor=NAVY, spaceBefore=4, spaceAfter=8))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12.5, textColor=NAVY_DARK, spaceBefore=10, spaceAfter=5))
styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.8, leading=14, textColor=INK, alignment=TA_LEFT, spaceAfter=6))
styles.add(ParagraphStyle("BodySmall", parent=styles["Normal"], fontSize=8.8, leading=12.5, textColor=SOFT))
styles.add(ParagraphStyle("GuideBullet", parent=styles["Body"], leftIndent=0, spaceAfter=3))
styles.add(ParagraphStyle("Caption", parent=styles["Normal"], fontSize=8.3, textColor=SOFT, alignment=1, spaceBefore=4, spaceAfter=10))
styles.add(ParagraphStyle("CellHead", parent=styles["Normal"], fontSize=8.6, textColor=colors.white, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8.8, textColor=INK, leading=12))
styles.add(ParagraphStyle("CalloutTitle", parent=styles["Normal"], fontSize=9.5, textColor=NAVY_DARK, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle("Callout", parent=styles["Normal"], fontSize=9.2, leading=13, textColor=INK))


def h1(text: str):
    return Paragraph(text, styles["H1"])


def h2(text: str):
    return Paragraph(text, styles["H2"])


def body(text: str):
    return Paragraph(text, styles["Body"])


def bullets(items: list[str]):
    return ListFlowable(
        [ListItem(Paragraph(item, styles["GuideBullet"]), leftIndent=6) for item in items],
        bulletType="bullet",
        start="circle",
        bulletFontSize=6,
        leftIndent=14,
    )


def numbered(items: list[str]):
    return ListFlowable(
        [ListItem(Paragraph(item, styles["GuideBullet"]), leftIndent=6) for item in items],
        bulletType="1",
        leftIndent=16,
    )


def chip_cell(label: str, tone: str) -> Table:
    palette = {
        "green": (GREEN, GREEN_SOFT),
        "amber": (AMBER, AMBER_SOFT),
        "red": (RED, RED_SOFT),
        "grey": (GREY, GREY_SOFT),
    }
    fg, bg = palette[tone]
    fg_hex = fg.hexval()[2:]
    t = Table([[Paragraph(f'<font color="#{fg_hex}"><b>{label}</b></font>', styles["Cell"])]])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def styled_table(header: list[str], rows: list[list], col_widths: list[float] | None = None) -> Table:
    data = [[Paragraph(f"<b>{c}</b>", styles["CellHead"]) for c in header]]
    for row in rows:
        data.append([c if isinstance(c, (Table, Paragraph)) else Paragraph(str(c), styles["Cell"]) for c in row])
    table = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def callout(title: str, text: str, tone_color=NAVY) -> Table:
    inner = Table(
        [[Paragraph(f'<font color="#{tone_color.hexval()[2:]}"><b>{title}</b></font> {text}', styles["Callout"])]],
        colWidths=[CONTENT_WIDTH - 14],
    )
    inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F8FB")),
                ("LINEBEFORE", (0, 0), (0, -1), 2.4, tone_color),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return inner


def screenshot(filename: str, caption: str):
    path = IMAGES_DIR / filename
    img = Image(str(path), width=CONTENT_WIDTH, height=CONTENT_WIDTH * 1000 / 1680)
    return KeepTogether([Spacer(1, 4), img, Paragraph(caption, styles["Caption"])])


def build() -> None:
    doc = SimpleDocTemplate(
        str(OUT_PATH),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="Settlement Matching and Geocoding Tool - User Guide",
    )

    elements: list = []

    # --- Cover ---
    elements.append(Spacer(1, 4 * cm))
    elements.append(Paragraph("USER GUIDE", ParagraphStyle("Eyebrow", parent=styles["Normal"], fontSize=10.5, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=10)))
    elements.append(Paragraph("Settlement Matching and Geocoding Tool", styles["CoverTitle"]))
    elements.append(Paragraph("For IM Officers, GIS Specialists, and Data Assistants", styles["CoverSubtitle"]))
    elements.append(Spacer(1, 10))
    elements.append(
        Paragraph(
            "This guide explains how to use the app from a data-operator's point of view: what to prepare, "
            "what each screen shows, what the numbers and colors mean, and what to do when a record doesn't "
            "match automatically. It assumes no coding knowledge.",
            styles["Body"],
        )
    )
    elements.append(Spacer(1, 16))
    badge_row = Table(
        [[
            Paragraph('<font color="#107C10"><b>&#9679;</b></font> Runs fully offline / Local Mode', styles["BodySmall"]),
            Paragraph("No coding required", styles["BodySmall"]),
            Paragraph("Streamlit desktop app", styles["BodySmall"]),
        ]],
        colWidths=[CONTENT_WIDTH / 3] * 3,
    )
    badge_row.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 0), 0.6, GRID),
                ("BOX", (1, 0), (1, 0), 0.6, GRID),
                ("BOX", (2, 0), (2, 0), 0.6, GRID),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(badge_row)
    elements.append(PageBreak())

    # --- What this tool does ---
    elements.append(h1("What this tool does"))
    elements.append(
        body(
            "The processor takes a partner's response spreadsheet (settlements visited, beneficiaries reached, "
            "etc.), matches any records missing GPS coordinates against a settlement gazetteer, validates the "
            "data for common quality problems, and produces cleaned Excel workbooks, GIS files (Shapefile, "
            "GeoPackage, GeoJSON), and QA reports &mdash; ready to hand off or load into ArcGIS, QGIS, or Power BI."
        )
    )
    elements.append(callout("Everything runs locally on the workstation.", "No response data, gazetteer, or coordinates are sent to any external server. The header always shows a Local Mode badge as a reminder of this.", GREEN))
    elements.append(Spacer(1, 6))
    elements.append(screenshot("01_landing.png", "Landing screen, before any file is loaded"))

    # --- Before you start ---
    elements.append(h1("Before you start: what you need"))
    elements.append(
        styled_table(
            ["Input", "Required?", "Must contain", "Notes"],
            [
                [Paragraph("<b>Response data</b>", styles["Cell"]), chip_cell("Required", "red"), "Settlement name, District", "Lat/long optional &mdash; missing coordinates are what matching fills in. .csv, .xlsx, .xls."],
                [Paragraph("<b>Settlement gazetteer</b>", styles["Cell"]), chip_cell("Required", "red"), "Settlement, District, Lat, Long", "Region recommended. Also accepts a spatial file (.geojson, .gpkg, .zip shapefile)."],
                [Paragraph("<b>District boundaries</b>", styles["Cell"]), chip_cell("Optional", "grey"), "&mdash;", "Adds a boundary overlay to the map. .geojson, .json, .gpkg, .zip."],
            ],
            col_widths=[110, 62, 130, CONTENT_WIDTH - 110 - 62 - 130],
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(body("You don't have to name columns exactly &mdash; common humanitarian naming variants are recognized automatically:"))
    elements.append(
        bullets(
            [
                "<b>Settlement</b> &rarr; settlement, village, site, location, town, &hellip;",
                "<b>District</b> &rarr; district, admin2, adm2_en, &hellip;",
                "<b>Region</b> &rarr; region, admin1, adm1_en, &hellip;",
                "<b>Latitude / Longitude</b> &rarr; lat/lon, y/x, gps_latitude/gps_longitude, &hellip;",
                "Optional fields like <b>partner</b>, <b>cluster/sector</b>, and <b>beneficiaries</b> are also detected and carried into outputs.",
            ]
        )
    )
    elements.append(body("If a required column can't be found, Data Validation (Step 2) says so explicitly and names the missing field."))
    elements.append(callout("No files yet?", "Click Load Sample Data in the sidebar for a ready-made example (12 response rows, 11 gazetteer settlements, 5 districts) and try the whole workflow before touching real data."))

    # --- Five-step workflow ---
    elements.append(h1("The five-step workflow"))
    elements.append(
        body(
            "The sidebar tracks progress through five stages &mdash; a stage turns green once complete, and the "
            "current one is highlighted. The same steps appear as a horizontal tracker at the top of the main panel."
        )
    )
    step_table = Table(
        [[Paragraph(f"<b>0{i}</b><br/>{label}", styles["Cell"]) for i, label in enumerate(
            ["Upload Data", "Data Validation", "Settlement Matching", "Review Matches", "Generate Outputs"], start=1
        )]],
        colWidths=[CONTENT_WIDTH / 5] * 5,
    )
    step_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF1FF")),
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(step_table)
    elements.append(PageBreak())

    # --- Step 1 ---
    elements.append(h1("Step 1 &mdash; Upload Data"))
    elements.append(body("In the sidebar:"))
    elements.append(
        bullets(
            [
                "<b>Load Sample Data</b> &mdash; instantly loads the bundled example dataset.",
                "<b>Upload files</b> (expandable) &mdash; three pickers: Response Excel/CSV, Settlement Gazetteer, District Boundary Layer (optional). Choose files, then click Load Uploaded Files.",
            ]
        )
    )
    elements.append(body("Once loaded, the Uploaded Files panel confirms what was read: file name, response row count, gazetteer settlement count, boundary district count."))
    elements.append(body("To start over completely, use <b>Restart Process</b> in the sidebar &mdash; it clears all loaded data, matches, and generated files."))

    # --- Step 2 ---
    elements.append(h1("Step 2 &mdash; Data Validation"))
    elements.append(body("Six at-a-glance metrics appear before matching runs."))
    elements.append(
        styled_table(
            ["Metric", "What it means"],
            [
                ["Total Records", "Rows read from the response file."],
                ["With Coordinates", "Already have valid lat/long &mdash; untouched by matching."],
                ["Missing Coordinates", "No GPS value &mdash; these go to settlement matching."],
                ["Duplicates", "Rows that look like repeats (same settlement, district, partner, cluster). Worth a manual check."],
                ["Invalid Coordinates", "Lat/long outside valid range (lat &minus;90 to 90, lon &minus;180 to 180) &mdash; likely swapped or mistyped."],
                ["Missing Settlement Name", "No settlement name at all &mdash; can't be auto-matched; fix at the source."],
            ],
            col_widths=[130, CONTENT_WIDTH - 130],
        )
    )
    elements.append(Spacer(1, 6))
    elements.append(body("The app also checks for districts absent from your gazetteer, and region/district pairs that don't match its hierarchy &mdash; both flagged as issues with a red (blocking) or yellow (worth reviewing) severity."))
    elements.append(callout("Practical tip:", "if Missing Settlement Name or Invalid Coordinates is non-zero, fix those in the source spreadsheet and re-upload &mdash; no automated step can recover a record with no name or an impossible coordinate.", AMBER))
    elements.append(screenshot("02_uploaded_validation.png", "Uploaded files and validation summary, right after loading data"))
    elements.append(PageBreak())

    # --- Step 3 ---
    elements.append(h1("Step 3 &mdash; Settlement Matching"))
    elements.append(body("Click <b>Run Settlement Matching</b> to attempt to geocode every response row missing coordinates."))
    elements.append(h2("How matching works, in order"))
    elements.append(
        numbered(
            [
                "<b>Approved alias</b> &mdash; if an analyst has previously confirmed this exact submitted name/district/region maps to a specific gazetteer entry, that confirmed answer is used first.",
                "<b>Exact match</b> &mdash; normalized settlement name matches the gazetteer exactly (tried with district+region, then district alone, then region alone, then nationally if the name is unique across the whole gazetteer).",
                "<b>RapidFuzz fuzzy match</b> (always on) &mdash; scores the closest gazetteer candidates by text similarity (district-constrained first, then region, then national), never stopping at just the first hit &mdash; the top 5 candidates are kept for comparison.",
                "<b>Semantic matching</b> (optional toggle) &mdash; a local Sentence Transformers embedding model (all-MiniLM-L6-v2) re-ranks that fuzzy shortlist by meaning, catching names worded differently but meaning the same place. First run downloads the model once.",
                "<b>Ollama reasoning notes</b> (optional toggle) &mdash; for “needs review” matches, asks a local Ollama LLM (qwen2.5) for a short plain-English note on which candidate looks most plausible and why &mdash; advisory only, it never changes the score or decision itself. Requires Ollama running locally (ollama serve); if unreachable, the app warns and simply skips this step.",
            ]
        )
    )
    elements.append(body("Both AI toggles are <b>off by default</b> and layer on top of RapidFuzz &mdash; never replace it. If a toggle is on but its dependency is missing, the app warns you and continues with RapidFuzz-only matching so a run never fails outright."))
    elements.append(h2("Confidence scoring and status"))
    elements.append(body("Every candidate is scored on up to six components; if one is unavailable (e.g. no submitted coordinate to check distance against), its weight shifts proportionally to whichever components are available &mdash; missing evidence is never scored as good or bad."))
    elements.append(
        styled_table(
            ["Component", "Weight"],
            [
                ["Settlement name similarity", "35%"],
                ["District consistency", "20%"],
                ["Region consistency", "10%"],
                ["Spatial consistency (distance)", "15%"],
                ["Historical evidence (prior approvals)", "10%"],
                ["Semantic similarity", "10%"],
            ],
            col_widths=[CONTENT_WIDTH - 100, 100],
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(
        styled_table(
            ["Confidence", "Status", "What happens"],
            [
                ["95-100%", chip_cell("Auto Matched", "green"), "Coordinates applied automatically &mdash; unless a hard safeguard below blocks it."],
                ["85-94.99%", chip_cell("Needs Review", "amber"), "Flagged for manual follow-up &mdash; see Step 4."],
                ["0-84.99%", chip_cell("Unmatched", "red"), "No confident candidate found."],
            ],
            col_widths=[70, 110, CONTENT_WIDTH - 70 - 110],
        )
    )
    elements.append(
        callout(
            "A high score alone is never enough:",
            "the app refuses to auto-accept &mdash; regardless of confidence &mdash; when there's a genuine district/region contradiction, the settlement name exists in more than one district with no way to tell them apart, the candidate is more than 15km from a submitted coordinate, the top two candidates are within 5 points of each other, this exact candidate has been rejected before for this context, or the candidate is missing required district/region data. A blocked match still lands in Needs Review rather than being downgraded further, so nothing is lost &mdash; it just isn't auto-applied.",
            AMBER,
        )
    )
    elements.append(screenshot("03_matching.png", "Needs Review queue, Compare Candidates panel, and outputs preview with the audit log"))
    elements.append(PageBreak())

    # --- Step 4 ---
    elements.append(h1("Step 4 &mdash; Review Matches"))
    elements.append(body("“Needs Review” and “Unmatched” records deserve attention &mdash; the app deliberately never auto-applies anything below 95% confidence (or that trips a hard safeguard), so a human always has the final say."))
    elements.append(h2("Needs Review Queue"))
    elements.append(body("Every needs-review/unmatched row appears in an editable table directly in the Settlement Matching panel. For each row you can:"))
    elements.append(
        bullets(
            [
                "<b>Accept</b> the suggested match as-is, or <b>Reject</b> it.",
                "<b>Edit</b> the suggested settlement, district, or coordinates directly in the table if you already know the right answer.",
                "Change the <b>Status</b> dropdown directly if needed.",
            ]
        )
    )
    elements.append(h2("Compare Candidates"))
    elements.append(body("Below the queue, pick any needs-review record from the dropdown to see the full ranked shortlist the pipeline considered for it side by side &mdash; not just the single top guess:"))
    elements.append(
        bullets(
            [
                "Settlement, district, region, and every score component (name/semantic/spatial/historical/confidence) for up to 5 candidates.",
                "Distance in km from a submitted coordinate, when one exists.",
                "Pick a different candidate from the dropdown and click <b>Use This Candidate</b> &mdash; this replaces the suggestion, marks the row accepted, and is what gets saved and taught back to the system (not the pipeline's original guess).",
            ]
        )
    )
    elements.append(body("When you accept a match (directly, or via Compare Candidates), the app remembers it: next time the same settlement name comes up in the same district/region, it's recognized instantly as an approved alias. Rejecting a candidate is remembered too, and repeatedly rejecting the same suggestion makes the app less confident in recommending it again."))
    elements.append(
        bullets(
            [
                "<b>Still can't resolve a record?</b> Fix the spelling at the source and re-run matching, turn on semantic matching if you haven't, check the QA Excel Report's “Low Confidence” sheet (Step 5), or source the coordinate manually and re-upload.",
            ]
        )
    )
    elements.append(body("Once satisfied, click <b>Save Reviewed Matches</b> and then <b>Apply Geocodes</b> (sidebar) to write accepted coordinates back into the working dataset used for outputs and the map."))

    # --- Map ---
    elements.append(h1("The Settlements Preview Map"))
    elements.append(body("A full-width, interactive view of every geocoded record sits below the matching and outputs panels."))
    elements.append(
        bullets(
            [
                "<b>Base layers</b> &mdash; switch between Light basemap, OpenStreetMap, Satellite imagery, and Topographic via the layer control (top right).",
                "<b>Overlays</b> &mdash; toggle district boundaries, settlement response records (clustered, colored by status), review candidates, and a new <b>submitted coordinates + distance</b> layer independently.",
                "<b>Submitted-to-candidate lines</b> &mdash; for records with an invalid (not merely missing) GPS value, a dashed line connects the original submitted point to the suggested candidate, labeled with the distance.",
                "<b>Conflict markers</b> &mdash; a review point gets a thicker dashed ring when it has a flagged administrative or spatial conflict, visible at a glance without opening the row.",
                "<b>Click any marker</b> for settlement name, district, match status, and confidence.",
                "<b>Zoom controls</b> (top left) plus normal scroll-wheel/drag, like any GIS viewer.",
                "<b>Fullscreen button</b> (top left) &mdash; expands the map to fill the browser window.",
                "<b>Mini-map</b> (bottom left) &mdash; shows your current viewport in the wider region.",
            ]
        )
    )
    elements.append(body("The map updates automatically as you load data, run matching, and apply geocodes &mdash; no manual refresh needed."))
    elements.append(screenshot("04_map.png", "Full-width map with legend, review candidates, and layer control open"))
    elements.append(PageBreak())

    # --- Step 5 ---
    elements.append(h1("Step 5 &mdash; Generate Outputs"))
    elements.append(body("Use <b>Outputs to generate</b> to choose which files you need (all selected by default), then click <b>Generate All Outputs</b> (or <b>Generate Selected Outputs</b> if narrowed down)."))
    elements.append(
        styled_table(
            ["Output", "Format", "Contents"],
            [
                ["District Data Sheets", "Excel", "One sheet per district with response records."],
                ["District Summary Sheet", "Excel", "Aggregated totals by district (and cluster, where available)."],
                ["Cleaned Response Data", "Excel", "Full response dataset with applied geocodes and match metadata."],
                ["Settlement Shapefile", "ESRI Shapefile (zipped)", "Point layer for GIS software."],
                ["GeoPackage", ".gpkg", "Same data, modern GIS format."],
                ["GeoJSON", ".geojson", "Web-GIS-friendly point layer."],
                ["QA Excel Report", "Excel", "Readiness metrics, validation issues, full match table, “Low Confidence” sheet, district/cluster summaries."],
                ["QA / Matching Report", "PDF", "Shareable summary of matching results and data quality."],
                ["Audit Log (CSV)", "CSV", "Every score component, the automatic decision, and any human review decision, reviewer, and note &mdash; one row per matched record."],
                ["Audit Log (Excel)", "Excel", "Same audit trail as the CSV, in workbook form."],
            ],
            col_widths=[120, 95, CONTENT_WIDTH - 120 - 95],
        )
    )
    elements.append(Spacer(1, 6))
    elements.append(body("A processing log (ocha_processing_log.txt) and a combined <b>Download All Outputs</b> ZIP are generated automatically alongside your selected files. Each output card shows Ready once generated, or an error message if a stage failed."))
    elements.append(screenshot("05_outputs.png", "Outputs generated and ready to download, including the new audit log"))
    elements.append(PageBreak())

    # --- Database Backup & Import ---
    elements.append(h1("Place Intelligence Database: Backup &amp; Import"))
    elements.append(
        body(
            "The app learns as you review: accepted matches become approved aliases, and rejections are "
            "remembered too, both stored locally in data/place_intelligence.db. A panel at the bottom of the "
            "dashboard lets you manage that history directly."
        )
    )
    elements.append(
        bullets(
            [
                "<b>Export Approved Aliases / Review History / Rejected Matches</b> &mdash; CSV downloads of each table.",
                "<b>Backup Full Database</b> &mdash; a complete copy of the raw database file.",
                "<b>Import</b> &mdash; upload a CSV/Excel alias list or a previous .db backup. Files are validated before anything is written, and imports merge with existing history (increasing approval counts on a repeat match) rather than silently overwriting it.",
            ]
        )
    )
    elements.append(
        callout(
            "Hosted deployments:",
            "unless the hosting platform provides persistent storage, this database resets on every restart/redeploy. Export a backup regularly if you're relying on accumulated alias history in a hosted instance.",
            AMBER,
        )
    )
    elements.append(screenshot("06_database.png", "Place Intelligence Database panel with export and import controls"))
    elements.append(PageBreak())

    # --- Sidebar reference ---
    elements.append(h1("Reading the sidebar at a glance"))
    elements.append(body("The sidebar's Information panel is a live dashboard of where you stand:"))
    elements.append(
        bullets(
            [
                "<b>Total Records</b> &mdash; rows in the response file.",
                "<b>Records with GPS</b> &mdash; already had valid coordinates on upload.",
                "<b>Missing GPS</b> &mdash; still need matching.",
                "<b>Matched</b> &mdash; auto-matched + needs-review records combined.",
                "<b>Needs Review</b> &mdash; subset of Matched not yet at auto-accept confidence.",
                "<b>Processed</b> &mdash; rows in the final dataset (outputs/map) after geocodes are applied.",
            ]
        )
    )
    elements.append(body("The Reference Data section above it reminds you which gazetteer and boundary files are currently loaded."))

    # --- FAQ ---
    elements.append(h1("Troubleshooting / FAQ"))
    faqs = [
        ("“sentence-transformers is not installed” warning", "Semantic matching was on but the package isn't available. The run still completes using RapidFuzz only. Ask whoever manages the installation to run pip install sentence-transformers, then try again."),
        ("“Ollama is not reachable at localhost:11434” warning", "Ollama reasoning notes were on, but no local Ollama server is running. The run still completes without the extra notes. To enable: install Ollama, run ollama pull qwen2.5, then ollama serve, and re-run matching."),
        ("A settlement I know exists isn't matching at all", "Check it's actually in the gazetteer (correct spelling, correct district). If genuinely missing, no amount of fuzzy or semantic matching will find it &mdash; add it to the gazetteer, or enter the coordinate manually."),
        ("The map shows fewer points than my total record count", "The map only plots rows with a valid coordinate. Rows still Needs Review or Unmatched won't appear until resolved (Step 4) and geocodes applied."),
        ("I want to start over with a different dataset", "Click Restart Process in the sidebar &mdash; clears loaded files, matches, and generated outputs without reloading the app."),
        ("Is any of my data leaving this computer?", "No. Core matching (RapidFuzz, Sentence Transformers) runs locally, and Ollama, if used, is also a local process. The header's Local Mode badge is a permanent reminder of this."),
        ("A match shows a high score but still landed in Needs Review", "One of the hard safeguards tripped &mdash; a district/region contradiction, an ambiguous name with no way to disambiguate it, excessive spatial distance, near-tied top candidates, a history of rejection for this exact context, or missing gazetteer metadata. Check Compare Candidates (Step 4) to see why; the safeguard is listed in the row's Reason text."),
    ]
    for question, answer in faqs:
        elements.append(Paragraph(question, ParagraphStyle("FAQQ", parent=styles["Body"], fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=2)))
        elements.append(body(answer))

    # --- Quick reference ---
    elements.append(h1("Quick reference"))
    elements.append(
        styled_table(
            ["Range", "Status"],
            [["95-100%", chip_cell("Auto Matched", "green")], ["85-94.99%", chip_cell("Needs Review", "amber")], ["0-84.99%", chip_cell("Unmatched", "red")]],
            col_widths=[100, CONTENT_WIDTH - 100],
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(
        styled_table(
            ["Color", "Meaning"],
            [
                [chip_cell("Green", "green"), "Auto-accepted / already geocoded"],
                [chip_cell("Amber", "amber"), "Needs review"],
                [chip_cell("Red", "red"), "Unresolved / invalid"],
                [chip_cell("Grey", "grey"), "Manually edited / rejected"],
            ],
            col_widths=[100, CONTENT_WIDTH - 100],
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(
        styled_table(
            ["Dataset", "Required fields"],
            [["Response data", "Settlement, District"], ["Gazetteer", "Settlement, District, Lat, Long"]],
            col_widths=[140, CONTENT_WIDTH - 140],
        )
    )

    doc.build(elements)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
