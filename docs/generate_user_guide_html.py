"""Builds the self-contained User Guide HTML from source content and screenshots.

Run this after the app's workflow, columns, or screenshots change (same
trigger as generate_user_guide_pdf.py, and normally run alongside it):

    .venv/Scripts/python docs/generate_user_guide_html.py

Output: static/user_guide.html, the file the header's "User Guide" button
links to when static/user_guide.pdf isn't present. Screenshots are embedded
as base64 data URIs so the file works standalone (no external assets, no
network) - the same offline-first requirement the rest of the app follows.
"""
from __future__ import annotations

import base64
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BASE_DIR / "docs" / "images"
OUT_PATH = BASE_DIR / "static" / "user_guide.html"


def _img_data_uri(filename: str) -> str:
    data = (IMAGES_DIR / filename).read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def e(text: str) -> str:
    """Escape the handful of characters that appear in plain body text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def chip(label: str, tone: str) -> str:
    return f'<span class="chip {tone}">{e(label)}</span>'


def table(headers: list[str], rows: list[list[str]]) -> str:
    head_html = "".join(f"<th>{e(h)}</th>" for h in headers)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>'


def bullets(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def callout(title: str, text: str, tone: str = "") -> str:
    cls = f"callout {tone}".strip()
    return f'<div class="{cls}"><strong>{e(title)}</strong> {text}</div>'


def figure(filename: str, caption: str) -> str:
    return (
        f'<figure><div class="shot"><img src="{_img_data_uri(filename)}" alt="{e(caption)}" loading="lazy"></div>'
        f"<figcaption>{e(caption)}</figcaption></figure>"
    )


def section(anchor: str, step_no: str, title: str, lede: str, body_html: str, wide: bool = False) -> str:
    step_span = f'<span class="step-no">{e(step_no)}</span>' if step_no else ""
    lede_html = f'<p class="lede">{lede}</p>' if lede else ""
    wide_cls = " wide" if wide else ""
    return (
        f'<section id="{anchor}" class="{wide_cls.strip()}">'
        f"<h2>{step_span}{e(title)}</h2>{lede_html}{body_html}</section>"
    )


CSS = """
:root {
  --bg: #F6F8FB; --paper: #FFFFFF; --paper-raised: #FFFFFF; --border: #E1E6EE;
  --ink: #142238; --ink-soft: #48566E; --ink-faint: #7C8AA3;
  --accent: #1D4ED8; --accent-ink: #14329E; --accent-soft: #EAF1FF;
  --status-green: #107C10; --status-green-soft: #E6F4E6;
  --status-amber: #9A6700; --status-amber-soft: #FFF4D9;
  --status-red: #C50F1F; --status-red-soft: #FCE8E9;
  --status-grey: #605E5C; --status-grey-soft: #EEEEED;
  --shadow: 0 1px 2px rgba(20, 34, 56, 0.04), 0 8px 24px rgba(20, 34, 56, 0.05);
  --font-display: "Segoe UI Semibold", "Segoe UI", system-ui, -apple-system, sans-serif;
  --font-body: "Segoe UI", system-ui, -apple-system, sans-serif;
  --font-mono: "Cascadia Code", "Consolas", ui-monospace, SFMono-Regular, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0A1220; --paper: #101A2C; --paper-raised: #142138; --border: #223049;
    --ink: #E9EFFB; --ink-soft: #AAB8D1; --ink-faint: #7688A8;
    --accent: #6EA1FF; --accent-ink: #BFD6FF; --accent-soft: rgba(110, 161, 255, 0.12);
    --status-green: #57C05B; --status-green-soft: rgba(87, 192, 91, 0.13);
    --status-amber: #F0B429; --status-amber-soft: rgba(240, 180, 41, 0.13);
    --status-red: #FF6B6B; --status-red-soft: rgba(255, 107, 107, 0.13);
    --status-grey: #A0AABC; --status-grey-soft: rgba(160, 170, 188, 0.13);
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.35);
  }
}
:root[data-theme="dark"] {
  --bg: #0A1220; --paper: #101A2C; --paper-raised: #142138; --border: #223049;
  --ink: #E9EFFB; --ink-soft: #AAB8D1; --ink-faint: #7688A8;
  --accent: #6EA1FF; --accent-ink: #BFD6FF; --accent-soft: rgba(110, 161, 255, 0.12);
  --status-green: #57C05B; --status-green-soft: rgba(87, 192, 91, 0.13);
  --status-amber: #F0B429; --status-amber-soft: rgba(240, 180, 41, 0.13);
  --status-red: #FF6B6B; --status-red-soft: rgba(255, 107, 107, 0.13);
  --status-grey: #A0AABC; --status-grey-soft: rgba(160, 170, 188, 0.13);
  --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.35);
}
:root[data-theme="light"] {
  --bg: #F6F8FB; --paper: #FFFFFF; --paper-raised: #FFFFFF; --border: #E1E6EE;
  --ink: #142238; --ink-soft: #48566E; --ink-faint: #7C8AA3;
  --accent: #1D4ED8; --accent-ink: #14329E; --accent-soft: #EAF1FF;
  --status-green: #107C10; --status-green-soft: #E6F4E6;
  --status-amber: #9A6700; --status-amber-soft: #FFF4D9;
  --status-red: #C50F1F; --status-red-soft: #FCE8E9;
  --status-grey: #605E5C; --status-grey-soft: #EEEEED;
  --shadow: 0 1px 2px rgba(20, 34, 56, 0.04), 0 8px 24px rgba(20, 34, 56, 0.05);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); line-height: 1.6; -webkit-font-smoothing: antialiased; }
a { color: var(--accent); }
::selection { background: var(--accent-soft); }
.shell { display: grid; grid-template-columns: 248px minmax(0, 1fr); gap: 0; max-width: 1320px; margin: 0 auto; }
.toc { position: sticky; top: 0; align-self: start; height: 100vh; overflow-y: auto; padding: 2rem 1.25rem 2rem 1.5rem; border-right: 1px solid var(--border); }
.toc-brand { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1.75rem; }
.toc-brand-mark { width: 30px; height: 30px; border-radius: 8px; background: var(--accent); color: #fff; display: flex; align-items: center; justify-content: center; font-family: var(--font-display); font-weight: 700; font-size: 0.85rem; flex-shrink: 0; }
.toc-brand strong { font-family: var(--font-display); font-size: 0.82rem; letter-spacing: 0.02em; display: block; line-height: 1.25; }
.toc-label { font-family: var(--font-display); font-size: 0.68rem; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase; color: var(--ink-faint); margin: 1.4rem 0 0.5rem; }
.toc-label:first-of-type { margin-top: 0; }
.toc nav { display: flex; flex-direction: column; gap: 0.15rem; }
.toc a { text-decoration: none; color: var(--ink-soft); font-size: 0.86rem; padding: 0.4rem 0.55rem; border-radius: 6px; display: flex; gap: 0.5rem; align-items: baseline; }
.toc a:hover { background: var(--accent-soft); color: var(--ink); }
.toc a .n { font-family: var(--font-mono); font-variant-numeric: tabular-nums; color: var(--accent); font-size: 0.78rem; width: 1.1rem; flex-shrink: 0; }
main { padding: 2.75rem clamp(1.25rem, 4vw, 4rem) 6rem; min-width: 0; }
.doc-header { margin-bottom: 2.75rem; }
.eyebrow { font-family: var(--font-display); font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); margin: 0 0 0.6rem; }
h1 { font-family: var(--font-display); font-weight: 700; font-size: clamp(1.7rem, 3vw, 2.35rem); letter-spacing: -0.01em; text-wrap: balance; margin: 0 0 0.5rem; }
.doc-header p { color: var(--ink-soft); font-size: 1.02rem; max-width: 62ch; margin: 0; }
.badge-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1.15rem; }
.badge { display: inline-flex; align-items: center; gap: 0.4rem; font-family: var(--font-mono); font-size: 0.76rem; padding: 0.3rem 0.65rem; border-radius: 999px; border: 1px solid var(--border); color: var(--ink-soft); background: var(--paper); }
.badge.local::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--status-green); flex-shrink: 0; }
section { max-width: 74ch; margin: 0 0 3rem; scroll-margin-top: 1.5rem; }
section.wide { max-width: none; }
h2 { font-family: var(--font-display); font-size: 1.3rem; font-weight: 700; letter-spacing: -0.005em; text-wrap: balance; margin: 0 0 0.2rem; padding-top: 0.2rem; display: flex; align-items: baseline; gap: 0.6rem; }
h2 .step-no { font-family: var(--font-mono); font-variant-numeric: tabular-nums; color: var(--accent); font-size: 1rem; font-weight: 600; }
h2 + .lede { color: var(--ink-soft); margin: 0.35rem 0 1.1rem; }
h3 { font-family: var(--font-display); font-size: 1.02rem; font-weight: 700; margin: 1.5rem 0 0.6rem; }
p { margin: 0 0 1rem; }
ul, ol { padding-left: 1.3rem; margin: 0 0 1rem; }
li { margin-bottom: 0.4rem; }
li:last-child { margin-bottom: 0; }
strong { font-weight: 650; }
code { font-family: var(--font-mono); background: var(--accent-soft); color: var(--accent-ink); padding: 0.1rem 0.4rem; border-radius: 5px; font-size: 0.86em; }
hr { border: none; border-top: 1px solid var(--border); margin: 0 0 3rem; }
.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; margin: 0 0 1.1rem; background: var(--paper); }
table { border-collapse: collapse; width: 100%; font-size: 0.89rem; }
th, td { text-align: left; padding: 0.6rem 0.85rem; border-bottom: 1px solid var(--border); vertical-align: top; }
th { font-family: var(--font-display); font-weight: 700; font-size: 0.74rem; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-faint); background: var(--accent-soft); white-space: nowrap; }
tr:last-child td { border-bottom: none; }
td .mono, td code { font-variant-numeric: tabular-nums; }
.chip { display: inline-flex; align-items: center; gap: 0.4rem; font-family: var(--font-display); font-weight: 700; font-size: 0.78rem; padding: 0.22rem 0.6rem; border-radius: 999px; white-space: nowrap; }
.chip::before { content: ""; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.chip.green { background: var(--status-green-soft); color: var(--status-green); }
.chip.green::before { background: var(--status-green); }
.chip.amber { background: var(--status-amber-soft); color: var(--status-amber); }
.chip.amber::before { background: var(--status-amber); }
.chip.red { background: var(--status-red-soft); color: var(--status-red); }
.chip.red::before { background: var(--status-red); }
.chip.grey { background: var(--status-grey-soft); color: var(--status-grey); }
.chip.grey::before { background: var(--status-grey); }
.callout { border: 1px solid var(--border); border-left: 3px solid var(--accent); background: var(--paper); border-radius: 8px; padding: 0.9rem 1.1rem; margin: 0 0 1.1rem; font-size: 0.92rem; color: var(--ink-soft); }
.callout strong { color: var(--ink); }
.callout.tip { border-left-color: var(--status-green); }
.callout.warn { border-left-color: var(--status-amber); }
figure { margin: 1.2rem 0 1.4rem; }
.shot { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; box-shadow: var(--shadow); background: var(--paper); }
.shot img { display: block; width: 100%; height: auto; }
figcaption { margin-top: 0.55rem; font-size: 0.82rem; color: var(--ink-faint); text-align: center; }
.steps-overview { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.7rem; margin: 0 0 1.1rem; }
.steps-overview .step { border: 1px solid var(--border); background: var(--paper); border-radius: 10px; padding: 0.85rem 0.8rem; }
.steps-overview .step .num { font-family: var(--font-mono); color: var(--accent); font-size: 0.78rem; font-variant-numeric: tabular-nums; }
.steps-overview .step strong { display: block; font-family: var(--font-display); font-size: 0.86rem; margin-top: 0.15rem; }
@media (max-width: 980px) {
  .shell { grid-template-columns: 1fr; }
  .toc { position: static; height: auto; border-right: none; border-bottom: 1px solid var(--border); }
  .steps-overview { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 560px) { .steps-overview { grid-template-columns: 1fr; } }
a:focus-visible, .toc a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
html { scroll-behavior: smooth; }
"""

TOC_ITEMS = [
    ("1", "what", "What this tool does"),
    ("2", "before", "Before you start"),
    ("3", "workflow", "The five-step workflow"),
    ("4", "step1", "Step 1 — Upload Data"),
    ("5", "step2", "Step 2 — Data Validation"),
    ("6", "step3", "Step 3 — Settlement Matching"),
    ("7", "step4", "Step 4 — Review Matches"),
    ("8", "map", "Settlements Preview Map"),
    ("9", "step5", "Step 5 — Generate Outputs"),
    ("9a", "database", "Place Intelligence Database"),
    ("10", "sidebar", "Reading the sidebar"),
    ("11", "faq", "Troubleshooting / FAQ"),
    ("12", "quickref", "Quick reference"),
]


def build() -> None:
    toc_nav = "".join(
        f'<a href="#{anchor}"><span class="n">{num}</span>{e(title)}</a>' for num, anchor, title in TOC_ITEMS
    )

    body_sections = []

    body_sections.append(
        section(
            "what",
            "1",
            "What this tool does",
            "",
            "<p>The processor takes a partner's response spreadsheet (settlements visited, beneficiaries reached, "
            "etc.), matches any records missing GPS coordinates against a settlement gazetteer, validates the "
            "data for common quality problems, and produces cleaned Excel workbooks, GIS files (Shapefile, "
            "GeoPackage, GeoJSON), and QA reports — ready to hand off or load into ArcGIS, QGIS, or Power BI.</p>"
            + callout(
                "Everything runs locally on the workstation.",
                "No response data, gazetteer, or coordinates are sent to any external server. The header always shows a Local Mode badge as a reminder of this.",
                "tip",
            )
            + figure("01_landing.png", "Landing screen, before any file is loaded"),
        )
    )

    body_sections.append(
        section(
            "before",
            "2",
            "Before you start: what you need",
            "",
            table(
                ["Input", "Required?", "Must contain", "Notes"],
                [
                    ["<strong>Response data</strong>", chip("Required", "red"), "Settlement name, District",
                     "Lat/long optional — missing coordinates are what matching fills in. .csv, .xlsx, .xls."],
                    ["<strong>Settlement gazetteer</strong>", chip("Required", "red"), "Settlement, District, Lat, Long",
                     "Region recommended. Also accepts a spatial file (.geojson, .gpkg, .zip shapefile) — points read from geometry."],
                    ["<strong>District boundaries</strong>", chip("Optional", "grey"), "—",
                     "Adds a boundary overlay to the map. .geojson, .json, .gpkg, .zip."],
                ],
            )
            + "<p>You don't have to name columns exactly — common humanitarian naming variants are recognized automatically:</p>"
            + bullets(
                [
                    "<strong>Settlement</strong> → <code>settlement</code>, <code>village</code>, <code>site</code>, <code>location</code>, <code>town</code>, <code>settlement_name</code>, …",
                    "<strong>District</strong> → <code>district</code>, <code>admin2</code>, <code>adm2_en</code>, …",
                    "<strong>Region</strong> → <code>region</code>, <code>admin1</code>, <code>adm1_en</code>, …",
                    "<strong>Latitude / Longitude</strong> → <code>lat</code>/<code>lon</code>, <code>y</code>/<code>x</code>, <code>gps_latitude</code>/<code>gps_longitude</code>, …",
                    "Optional columns like <strong>partner</strong>, <strong>cluster/sector</strong>, and <strong>beneficiaries reached</strong> are detected too, and carried through into outputs and summary sheets.",
                ]
            )
            + callout(
                "Don't have your own files yet?",
                "Click <strong>Load Sample Data</strong> in the sidebar to load a ready-made example and try the whole workflow before using real data.",
            ),
        )
    )

    body_sections.append(
        section(
            "workflow",
            "3",
            "The five-step workflow",
            "The left sidebar tracks your progress through five stages, echoed as a horizontal tracker at the top of the main panel.",
            '<div class="steps-overview">'
            + "".join(
                f'<div class="step"><span class="num">{i}</span><strong>{e(t)}</strong></div>'
                for i, t in enumerate(
                    ["Upload Data", "Data Validation", "Settlement Matching", "Review Matches", "Generate Outputs"], start=1
                )
            )
            + "</div>",
        )
    )

    body_sections.append(
        section(
            "step1",
            "4",
            "Step 1 — Upload Data",
            "",
            "<p>In the sidebar:</p>"
            + bullets(
                [
                    "<strong>Load Sample Data</strong> — instantly loads the bundled example dataset.",
                    "<strong>Upload files</strong> (expandable) — three file pickers: Response Excel or CSV, Settlement Gazetteer, District Boundary Layer (optional). Choose your files, then click <strong>Load Uploaded Files</strong>.",
                ]
            )
            + "<p>Once loaded, the <strong>Uploaded Files</strong> panel confirms what was read: file name, row count, settlement count, district count.</p>"
            + "<p>Need to start over? <strong>Restart Process</strong> in the sidebar clears all loaded data, matches, and generated files.</p>",
        )
    )

    body_sections.append(
        section(
            "step2",
            "5",
            "Step 2 — Data Validation",
            "Before matching runs, the Data Validation Summary gives you six at-a-glance metrics.",
            table(
                ["Metric", "What it means"],
                [
                    ["<strong>Total Records</strong>", "Rows read from the response file."],
                    ["<strong>With Coordinates</strong>", "Rows that already have valid latitude/longitude — left untouched by matching."],
                    ["<strong>Missing Coordinates</strong>", "Rows with no GPS value — these go to settlement matching."],
                    ["<strong>Duplicates</strong>", "Rows that look like repeats (same settlement, district, partner, cluster)."],
                    ["<strong>Invalid Coordinates</strong>", "Latitude/longitude outside valid ranges — likely a swapped or mistyped value."],
                    ["<strong>Missing Settlement Name</strong>", "Rows with no settlement name — can't be matched automatically."],
                ],
            )
            + callout(
                "Practical tip:",
                "if “Missing Settlement Name” or “Invalid Coordinates” is non-zero, fix those in the source spreadsheet and re-upload — no automated step can recover a record with no name or an impossible coordinate.",
                "warn",
            )
            + figure("02_uploaded_validation.png", "Uploaded files and validation summary after loading data"),
        )
    )

    body_sections.append(
        section(
            "step3",
            "6",
            "Step 3 — Settlement Matching",
            "Click Run Settlement Matching to attempt to geocode every response row that's missing coordinates.",
            "<h3>How matching works, in order</h3>"
            + "<ol>"
            + "".join(
                f"<li>{item}</li>"
                for item in [
                    "<strong>Approved alias</strong> — a previously confirmed submitted name/district/region → gazetteer entry is used first.",
                    "<strong>Exact match</strong> — normalized settlement name matches the gazetteer exactly (district+region, then district, then region, then nationally if unique).",
                    "<strong>RapidFuzz fuzzy match</strong> (always on) — scores the closest candidates by text similarity, keeping the top 5 for comparison.",
                    "<strong>Semantic matching</strong> (optional toggle) — a local Sentence Transformers embedding model (all-MiniLM-L6-v2) re-ranks the fuzzy shortlist by meaning.",
                    "<strong>Ollama reasoning notes</strong> (optional toggle) — a local Ollama LLM (qwen2.5) adds a short plain-English note for “needs review” matches. Purely advisory.",
                ]
            )
            + "</ol>"
            + "<p>Both AI toggles are <strong>off by default</strong> and layer on top of RapidFuzz — they never replace it. If a toggle is on but unavailable, the app warns you and continues with RapidFuzz-only matching.</p>"
            + "<h3>Confidence scoring and status</h3>"
            + "<p>Every candidate gets a confidence score (0–100%) from up to six components. A missing component's weight shifts proportionally to whichever are available — missing evidence is never scored as good or bad.</p>"
            + table(
                ["Component", "Weight"],
                [
                    ["Settlement name similarity", "35%"],
                    ["District consistency", "20%"],
                    ["Region consistency", "10%"],
                    ["Spatial consistency (distance)", "15%"],
                    ["Historical evidence (prior approvals)", "10%"],
                    ["Semantic similarity", "10%"],
                ],
            )
            + table(
                ["Confidence", "Status", "What happens"],
                [
                    ["90–100%", chip("Auto Matched", "green"), "Coordinates applied automatically — unless a hard safeguard blocks it."],
                    ["85–89.99%", chip("Needs Review", "amber"), "Flagged for manual follow-up — see Step 4."],
                    ["Below 85%", chip("Unmatched", "red"), "No confident candidate was found."],
                ],
            )
            + callout(
                "A high score alone is never enough:",
                "the app refuses to auto-accept — regardless of confidence — when there's a district/region contradiction, an ambiguous name with no way to disambiguate it, the candidate is more than 15km from a submitted coordinate, the top two candidates are within 5 points of each other, this exact candidate was rejected before for this context, or it's missing required district/region data. A blocked match still lands in Needs Review rather than being downgraded further.",
                "warn",
            )
            + figure("03_matching.png", "Needs Review queue with bulk actions, Compare Candidates panel, and outputs preview"),
        )
    )

    body_sections.append(
        section(
            "step4",
            "7",
            "Step 4 — Review Matches",
            "“Needs Review” and “Unmatched” records deserve attention — the app deliberately never auto-applies anything below 90% confidence (or that trips a hard safeguard), so a human always has the final say.",
            "<h3>Needs Review Queue</h3>"
            + "<p>Every needs-review/unmatched row appears in an editable table. For each row you can:</p>"
            + bullets(
                [
                    "<strong>Accept</strong> the suggested match as-is, or <strong>Reject</strong> it.",
                    "<strong>Edit</strong> the suggested settlement, district, or coordinates directly if you already know the right answer.",
                    "Change the <strong>Status</strong> dropdown directly if needed.",
                ]
            )
            + callout(
                "Reviewing a large batch?",
                "Two tools above the table cut down on row-by-row clicking: drag the confidence slider to a cutoff and click <strong>Check Accept ≥ Threshold</strong> or <strong>Check Reject &lt; Threshold</strong> to tick every matching row at once (nothing is written until you click Save Reviewed Matches) — and use <strong>Sort queue by</strong> to work through the highest-confidence matches first instead of upload order.",
            )
            + "<h3>Compare Candidates</h3>"
            + "<p>Below the queue, pick any needs-review record to see the full ranked shortlist the pipeline considered for it — not just the single top guess:</p>"
            + bullets(
                [
                    "Settlement, district, region, and every score component for up to 5 candidates.",
                    "Distance in km from a submitted coordinate, when one exists.",
                    "Pick a different candidate and click <strong>Use This Candidate</strong> — replaces the suggestion and marks the row accepted.",
                    "Or click <strong>Reject This Record</strong> to reject it outright without picking an alternate.",
                ]
            )
            + callout(
                "Review from the map instead:",
                "on the Settlements Preview Map (below), clicking any red or yellow circle jumps straight to that record in this Compare Candidates panel — with the settlement's real-world location still visible while you decide.",
            )
            + "<p>When you accept a match — directly, via Compare Candidates, or via a map click — the app remembers it: next time the same settlement name comes up in the same district/region, it's recognized instantly as an approved alias. Rejecting a candidate is remembered too.</p>"
            + "<h3>Still can't resolve a record?</h3>"
            + bullets(
                [
                    "<strong>Fix the spelling at the source</strong> and re-run matching — most “needs review” cases are a spelling/transliteration difference.",
                    "<strong>Turn on semantic matching</strong> if you haven't — it often resolves near-miss spellings RapidFuzz alone scores lower.",
                    "<strong>Check the QA Excel Report's “Low Confidence” sheet</strong> (Step 5) — lists every needs-review/unmatched record with its suggested candidate.",
                    "<strong>Source the coordinate manually</strong> and re-upload — the most reliable fix for settlements genuinely missing from the gazetteer.",
                ]
            )
            + "<p>Once satisfied, click <strong>Save Reviewed Matches</strong> then <strong>Apply Geocodes</strong> (sidebar) to write accepted coordinates back into the working dataset.</p>",
        )
    )

    body_sections.append(
        section(
            "map",
            "8",
            "The Settlements Preview Map",
            "A full-width, interactive view of every geocoded record sits below the matching and outputs panels.",
            bullets(
                [
                    "<strong>Base layers</strong> — Light basemap, OpenStreetMap, Satellite imagery, Topographic (layer control, top right).",
                    "<strong>Overlays</strong> — toggle district boundaries, settlement response records (clustered, colored by status), review candidates, and a submitted coordinates + distance layer independently.",
                    "<strong>Submitted-to-candidate lines</strong> — for records with an invalid (not merely missing) GPS value, a dashed line connects the original point to the suggested candidate, labeled with the distance.",
                    "<strong>Conflict markers</strong> — a review point gets a thicker dashed ring when it has a flagged administrative or spatial conflict.",
                    "<strong>Click any marker</strong> for a popup with settlement name, district, match status, and confidence.",
                    "<strong>Click a red or yellow review-candidate marker</strong> to open that exact record in the Compare Candidates panel above (Step 4) — review it with its real-world location still on screen.",
                    "<strong>Zoom controls</strong> (top left) plus normal scroll-wheel/drag, like any GIS viewer.",
                    "<strong>Fullscreen button</strong> (top left) — expands the map to fill the browser window.",
                    "<strong>Mini-map</strong> (bottom left) — shows your current viewport in the wider region.",
                ]
            )
            + "<p>The map updates automatically as you load data, run matching, and apply geocodes — no manual refresh needed.</p>"
            + figure("04_map.png", "Full-width map with legend, layer control, and review-candidate markers"),
            wide=True,
        )
    )

    body_sections.append(
        section(
            "step5",
            "9",
            "Step 5 — Generate Outputs",
            "Choose which files you need in Outputs to generate (all selected by default), then click Generate All Outputs.",
            table(
                ["Output", "Format", "Contents"],
                [
                    ["District Data Sheets", "Excel", "One sheet per district with response records, rows colored by cluster."],
                    ["District Summary Sheet", "Excel", "Aggregated totals by district (and cluster, where available)."],
                    ["Cleaned Response Data", "Excel", "Full response dataset with applied geocodes and match metadata."],
                    ["Settlement Shapefile", "ESRI Shapefile (zipped)", "Point layer, every field, for GIS software."],
                    ["GeoPackage", ".gpkg", "Same data, modern GIS format."],
                    ["GeoJSON", ".geojson", "Web-GIS-friendly point layer."],
                    ["QA Excel Report", "Excel", "Readiness metrics, validation issues, full match table, “Low Confidence” sheet, district/cluster summaries."],
                    ["QA / Matching Report", "PDF", "Shareable summary of matching results and data quality."],
                    ["Audit Log (CSV / Excel)", "CSV / Excel", "Every score component, automatic decision, and any human review decision, reviewer, and note."],
                ],
            )
            + "<p>A processing log and a combined <strong>Download All Outputs</strong> ZIP are generated automatically. Each output card shows <strong>Ready</strong> once generated.</p>"
            + figure("05_outputs.png", "Outputs generated and ready to download"),
        )
    )

    body_sections.append(
        section(
            "database",
            "9a",
            "Place Intelligence Database: Backup & Import",
            "The app learns as you review: accepted matches become approved aliases, and rejections are remembered too, both stored locally.",
            bullets(
                [
                    "<strong>Export Approved Aliases / Review History / Rejected Matches</strong> — CSV downloads of each table.",
                    "<strong>Backup Full Database</strong> — a complete copy of the raw database file.",
                    "<strong>Import</strong> — upload a CSV/Excel alias list or a previous .db backup. Files are validated before anything is written, and imports merge with existing history rather than overwriting it.",
                ]
            )
            + callout(
                "Hosted deployments:",
                "unless the hosting platform provides persistent storage, this database resets on every restart/redeploy. Export a backup regularly if you're relying on accumulated alias history in a hosted instance.",
                "warn",
            )
            + figure("06_database.png", "Place Intelligence Database panel with export and import controls"),
        )
    )

    body_sections.append(
        section(
            "sidebar",
            "10",
            "Reading the sidebar at a glance",
            "The sidebar's Information panel is a live dashboard of where you stand.",
            bullets(
                [
                    "<strong>Total Records</strong> — rows in the response file.",
                    "<strong>Records with GPS</strong> — already had valid coordinates on upload.",
                    "<strong>Missing GPS</strong> — still need matching.",
                    "<strong>Matched</strong> — auto-matched + needs-review records combined.",
                    "<strong>Needs Review</strong> — subset of Matched not yet at auto-accept confidence.",
                    "<strong>Processed</strong> — rows in the final processed dataset after geocodes are applied.",
                ]
            ),
        )
    )

    faq_items = [
        ("“sentence-transformers is not installed” warning", "Semantic matching was on but the package isn't available. The run still completes using RapidFuzz only. Ask whoever manages the installation to run <code>pip install sentence-transformers</code>, then try again."),
        ("“Ollama is not reachable at localhost:11434” warning", "Ollama reasoning notes were on, but no local Ollama server is running. The run still completes without the extra notes. To enable: install Ollama, run <code>ollama pull qwen2.5</code>, then <code>ollama serve</code>, and re-run matching."),
        ("A settlement I know exists isn't matching at all", "Check it's actually in the gazetteer (correct spelling, correct district). If genuinely missing, no amount of fuzzy or semantic matching will find it — add it to the gazetteer, or enter the coordinate manually."),
        ("The map shows fewer points than my total record count", "The map only plots rows with a valid coordinate. Rows still Needs Review or Unmatched won't appear until resolved (Step 4) and geocodes applied."),
        ("I want to start over with a different dataset", "Click <strong>Restart Process</strong> in the sidebar — clears loaded files, matches, and generated outputs without reloading the app."),
        ("Is any of my data leaving this computer?", "No. Core matching (RapidFuzz, Sentence Transformers) runs locally, and Ollama, if used, is also a local process. The header's Local Mode badge is a permanent reminder of this."),
        ("A match shows a high score but still landed in Needs Review", "One of the hard safeguards tripped — a district/region contradiction, an ambiguous name with no way to disambiguate it, excessive spatial distance, near-tied top candidates, a history of rejection for this exact context, or missing gazetteer metadata. Check Compare Candidates (Step 4) to see why."),
    ]
    faq_html = "".join(
        f"<h3>{e(q)}</h3><p>{a}</p>" for q, a in faq_items
    )
    body_sections.append(section("faq", "11", "Troubleshooting / FAQ", "", faq_html))

    body_sections.append(
        section(
            "quickref",
            "12",
            "Quick reference",
            "",
            table(
                ["Range", "Status"],
                [
                    ["90–100%", chip("Auto Matched", "green")],
                    ["85–89.99%", chip("Needs Review", "amber")],
                    ["Below 85%", chip("Unmatched", "red")],
                ],
            )
            + table(
                ["Color", "Meaning"],
                [
                    [chip("Green", "green"), "Auto-accepted / already geocoded"],
                    [chip("Amber", "amber"), "Needs review"],
                    [chip("Red", "red"), "Unresolved / invalid"],
                    [chip("Grey", "grey"), "Manually edited / rejected"],
                ],
            )
            + table(
                ["Dataset", "Required fields"],
                [
                    ["Response data", "Settlement, District"],
                    ["Gazetteer", "Settlement, District, Latitude, Longitude"],
                ],
            ),
        )
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Settlement Matching and Geocoding Tool — User Guide</title>
<style>{CSS}</style>
</head>
<body>
<div class="shell">
  <aside class="toc">
    <div class="toc-brand">
      <div class="toc-brand-mark">OC</div>
      <strong>Settlement Matching &amp; Geocoding Tool</strong>
    </div>
    <div class="toc-label">Guide</div>
    <nav>{toc_nav}</nav>
  </aside>
  <main>
    <div class="doc-header">
      <p class="eyebrow">User Guide</p>
      <h1>Settlement Matching and Geocoding Tool</h1>
      <p>For IM Officers, GIS Specialists, and Data Assistants. This guide explains how to use the app from a data-operator's point of view: what to prepare, what each screen shows, what the numbers and colors mean, and what to do when a record doesn't match automatically. It assumes no coding knowledge.</p>
      <div class="badge-row">
        <span class="badge local">Runs fully offline / Local Mode</span>
        <span class="badge">No coding required</span>
        <span class="badge">Streamlit desktop app</span>
      </div>
    </div>
    {''.join(body_sections)}
  </main>
</div>
</body>
</html>
"""
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
