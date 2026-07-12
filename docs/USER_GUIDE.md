# Settlement Matching and Geocoding Tool — User Guide

**For IM Officers, GIS Specialists, and Data Assistants**

This guide explains how to use the app from a data-operator's point of view: what to prepare, what each screen shows, what the numbers and colors mean, and what to do when a record doesn't match automatically. It assumes no coding knowledge.

---

## 1. What this tool does

The processor takes a partner's response spreadsheet (settlements visited, beneficiaries reached, etc.), matches any records that are missing GPS coordinates against a settlement gazetteer, validates the data for common quality problems, and produces cleaned Excel workbooks, GIS files (Shapefile, GeoPackage, GeoJSON), and QA reports — ready to hand off or load into ArcGIS/QGIS/Power BI.

Everything runs **locally on the workstation**. No response data, gazetteer, or coordinates are sent to any external server. The header always shows a **Local Mode** badge as a reminder of this.

![Landing screen before any file is loaded](images/01_landing.png)

---

## 2. Before you start: what you need

| Input | Required? | Must contain | Notes |
|---|---|---|---|
| **Response data** | Required | Settlement name, District | Latitude/longitude are optional — missing coordinates are what the matching step fills in. Accepts `.csv`, `.xlsx`, `.xls`. |
| **Settlement gazetteer** | Required | Settlement name, District, Latitude, Longitude | Region is recommended, improves match accuracy. Accepts `.csv`, `.xlsx`, `.xls`, or a spatial file (`.geojson`, `.gpkg`, `.zip` shapefile) — point locations are read from the geometry. |
| **District boundary layer** | Optional | — | Adds a boundary overlay to the map. Accepts `.geojson`, `.json`, `.gpkg`, `.zip`. |

You don't have to name your columns exactly. The app recognizes common humanitarian naming variants automatically, for example:

- **Settlement** → `settlement`, `village`, `site`, `location`, `town`, `settlement_name`, …
- **District** → `district`, `admin2`, `adm2_en`, …
- **Region** → `region`, `admin1`, `adm1_en`, …
- **Latitude / Longitude** → `lat`/`lon`, `y`/`x`, `gps_latitude`/`gps_longitude`, …
- Optional columns like **partner**, **cluster/sector**, and **beneficiaries reached** are also detected and carried through into the outputs and summary sheets when present.

If a required column can't be found, the Data Validation step (Step 2) will say so explicitly and name the missing field.

**Don't have your own files yet?** Click **Load Sample Data** in the sidebar to load a ready-made example (12 response rows, 11 gazetteer settlements, 5 districts) and try the whole workflow end-to-end before using real data.

---

## 3. The five-step workflow

The left sidebar tracks your progress through five stages. A stage turns green (**OK**) once it's complete, and the current stage is highlighted:

1. **Upload Data** — load the response file, gazetteer, and optional boundaries.
2. **Data Validation** — review data-quality indicators before matching.
3. **Settlement Matching** — auto-match records that are missing coordinates.
4. **Review Matches** — check anything the matcher wasn't confident about.
5. **Generate Outputs** — produce and download the cleaned files and reports.

The same five steps are echoed as a horizontal **Process Overview** tracker at the top of the main panel.

---

## 4. Step 1 — Upload Data

In the sidebar:

- **Load Sample Data** — instantly loads the bundled example dataset.
- **Upload files** (expandable) — three file pickers: *Response Excel or CSV*, *Settlement Gazetteer*, *District Boundary Layer* (optional). Choose your files, then click **Load Uploaded Files**.

Once loaded, the **Uploaded Files** panel at the top confirms what was read: file name, row count for the response data, settlement count for the gazetteer, and district count for the boundary layer.

If you need to start over completely, use **Restart Process** in the sidebar — it clears all loaded data, matches, and generated files.

---

## 5. Step 2 — Data Validation

Before matching runs, the **Data Validation Summary** gives you six at-a-glance metrics:

| Metric | What it means |
|---|---|
| **Total Records** | Rows read from the response file. |
| **With Coordinates** | Rows that already have valid latitude/longitude — these are left untouched by matching. |
| **Missing Coordinates** | Rows with no GPS value — these are the ones sent to settlement matching. |
| **Duplicates** | Rows that look like repeats (same settlement, district, partner, and cluster). Worth a manual check before reporting. |
| **Invalid Coordinates** | Rows with a latitude/longitude outside valid ranges (lat must be −90 to 90, lon −180 to 180) — likely a swapped or mistyped value. |
| **Missing Settlement Name** | Rows with no settlement name at all — these can't be matched automatically and need to be fixed at the source. |

Behind the scenes the app also checks for districts that don't exist in your gazetteer, and region/district combinations that don't match the gazetteer's hierarchy — both are flagged as issues if found, along with a red/yellow severity so you know what's blocking (red) versus worth reviewing (yellow).

**Practical tip:** if "Missing Settlement Name" or "Invalid Coordinates" is non-zero, fix those in the source spreadsheet and re-upload — no automated step can recover a record with no name or an impossible coordinate.

![Uploaded files and validation summary after loading data](images/02_uploaded_validation.png)

---

## 6. Step 3 — Settlement Matching

Click **Run Settlement Matching** (in the sidebar, or the button of the same name above the matching table) to attempt to geocode every response row that's missing coordinates.

### How matching works, in order

1. **Approved alias** — if an analyst has previously confirmed this exact submitted name/district/region maps to a specific gazetteer entry, that confirmed answer is used first.
2. **Exact match** — normalized settlement name matches the gazetteer exactly (tried with district+region, then district alone, then region alone, then nationally if the name is unique gazetteer-wide).
3. **RapidFuzz fuzzy match** *(always on)* — scores the closest gazetteer candidates by text similarity (district-constrained first, then region, then national), keeping the top 5 for comparison rather than stopping at the first hit.
4. **Semantic matching** *(optional toggle)* — uses a local Sentence Transformers embedding model (`all-MiniLM-L6-v2`) to re-rank that fuzzy shortlist by meaning, catching names worded differently but meaning the same place. Adds a moment of processing time the first time it runs (it downloads the model once).
5. **Ollama reasoning notes** *(optional toggle)* — for any match that lands in "needs review," asks a local Ollama LLM (`qwen2.5`) for a short, plain-English note on which candidate looks most plausible and why. Purely advisory — it never changes the score or decision itself. Requires Ollama installed and running on the same machine (`ollama serve`) — if it isn't reachable, the app shows a warning and simply skips this step rather than failing.

Both AI toggles are **off by default** and layer on top of RapidFuzz — they never replace it. If a toggle is on but its dependency isn't installed or reachable, the app warns you and continues with RapidFuzz-only matching so a run never fails outright.

### Confidence scoring and status

Every candidate gets a confidence score (0–100%) from up to six components. If one is unavailable (e.g. no submitted coordinate to check distance against), its weight shifts proportionally to whichever components are available — missing evidence is never scored as good or bad.

| Component | Weight |
|---|---|
| Settlement name similarity | 35% |
| District consistency | 20% |
| Region consistency | 10% |
| Spatial consistency (distance) | 15% |
| Historical evidence (prior approvals) | 10% |
| Semantic similarity | 10% |

| Confidence | Status | What happens |
|---|---|---|
| **90–100%** | 🟢 Auto Matched | Coordinates are applied automatically — unless a hard safeguard below blocks it. |
| **85–89.99%** | 🟠 Needs Review | Flagged for manual follow-up — see Step 4 below. |
| **Below 85%** | 🔴 Unmatched | No confident candidate was found. |

**A high score alone is never enough.** The app refuses to auto-accept — regardless of confidence — when there's a genuine district/region contradiction, the settlement name exists in more than one district with no way to disambiguate it, the candidate is more than 15km from a submitted coordinate, the top two candidates are within 5 points of each other, this exact candidate has been rejected before for this context, or the candidate is missing required district/region data. A blocked match still lands in Needs Review rather than being downgraded further.

The matching table shows submitted settlement/district, the suggested match, confidence, latitude/longitude, and a color-coded pill. The legend below the table (Auto Matched / Needs Review / Unmatched / Manually Edited) always shows current counts.

![Needs Review queue, Compare Candidates panel, and outputs preview with the audit log](images/03_matching.png)

---

## 7. Step 4 — Review Matches

"Needs Review" and "Unmatched" records are the ones worth your attention — the app deliberately does **not** auto-apply anything below 90% confidence (or that trips a hard safeguard), so a human always has the final say.

### Needs Review Queue

Every needs-review/unmatched row appears in an editable table directly in the Settlement Matching panel. For each row you can:

- **Accept** the suggested match as-is, or **Reject** it.
- **Edit** the suggested settlement, district, or coordinates directly if you already know the right answer.
- Change the **Status** dropdown directly if needed.

**Reviewing a large batch?** Two tools sit above the table to cut down on row-by-row clicking:

- **Bulk accept/reject by threshold** — drag the confidence slider to a cutoff, then click **Check Accept ≥ Threshold** to tick Accept on every row at or above it in one go, or **Check Reject < Threshold** to tick Reject on everything below it. Nothing is written until you click **Save Reviewed Matches** — this only pre-fills the checkboxes so you can scan the result before committing.
- **Sort queue by** — reorder the table by confidence (high-to-low or low-to-high) or by row ID, so you can work through the most likely matches first instead of scrolling through the queue in upload order.

### Compare Candidates

Below the queue, pick any needs-review record from the dropdown to see the full ranked shortlist the pipeline considered for it — not just the single top guess:

- Settlement, district, region, and every score component (name/semantic/spatial/historical/confidence) for up to 5 candidates.
- Distance in km from a submitted coordinate, when one exists.
- Pick a different candidate from the dropdown and click **Use This Candidate** — this replaces the suggestion, marks the row accepted, and is what gets saved and taught back to the system (not the pipeline's original guess).
- Or click **Reject This Record** to reject it outright without picking an alternate candidate.

**Review from the map instead:** on the Settlements Preview Map (Section 8 below), clicking any red or yellow circle jumps straight to that record in this Compare Candidates panel — with the settlement's real-world location still visible on the map while you decide, instead of cross-referencing row IDs against the table.

When you accept a match — directly, via Compare Candidates, or via a map click — the app remembers it: next time the same settlement name comes up in the same district/region, it's recognized instantly as an approved alias. Rejecting a candidate is remembered too, and repeatedly rejecting the same suggestion makes the app less confident in recommending it again.

**Still can't resolve a record?**

- **Fix the spelling at the source.** Most "needs review" cases are a spelling or transliteration difference (e.g. "Deynile" vs. "Deeyniile"). Correct the settlement/district name in the response file and re-run matching.
- **Turn on semantic matching** if you haven't — it often resolves near-miss spellings that RapidFuzz alone scores lower.
- **Check the QA Excel Report's "Low Confidence" sheet** (generated in Step 5) — it lists every needs-review/unmatched record with its suggested candidate side by side.
- **Source the coordinate manually** and enter it directly into the response file, then re-upload — the most reliable fix for settlements genuinely missing from the gazetteer.

Once you're satisfied with the matches, click **Save Reviewed Matches** and then **Apply Geocodes** (sidebar) to write the accepted coordinates back into the working dataset used for outputs and the map.

---

## 8. The Settlements Preview Map

Below the matching and outputs panels, the **Settlements Preview Map** gives you a full-width, interactive view of every geocoded record:

- **Base layers** — switch between Light basemap, OpenStreetMap, Satellite imagery, and Topographic using the layer control (top right).
- **Overlays** — toggle district boundaries, settlement response records (clustered markers, colored by match status), review candidates, and a **submitted coordinates + distance** layer independently.
- **Submitted-to-candidate lines** — for records with an invalid (not merely missing) GPS value, a dashed line connects the original submitted point to the suggested candidate, labeled with the distance.
- **Conflict markers** — a review point gets a thicker dashed ring when it has a flagged administrative or spatial conflict, visible at a glance.
- **Click any marker** for a popup with settlement name, district, match status, and confidence.
- **Click a red or yellow "Review candidates" marker** to open that exact record in the Compare Candidates panel above (Step 4) — a quick way to review with the settlement's real-world location still in view, without hunting for its row in the table.
- **Zoom controls** (top left) and normal scroll-wheel/drag zoom and pan, like any GIS viewer.
- **Fullscreen button** (top left, expand icon) — opens the map to fill the browser window, useful when working with a large or dense dataset.
- **Mini-map** (bottom left) — shows your current viewport in the context of the wider region.

The map updates automatically as you load data, run matching, and apply geocodes — no manual refresh needed.

![Full-width interactive map with legend, review candidates, and layer control open](images/04_map.png)

---

## 9. Step 5 — Generate Outputs

Use the **Outputs to generate** multiselect to choose which files you need (all are selected by default), then click **Generate All Outputs** (or **Generate Selected Outputs** if you've narrowed the list).

| Output | Format | Contents |
|---|---|---|
| **District Data Sheets** | Excel workbook | One sheet per district with response records. |
| **District Summary Sheet** | Excel | Aggregated totals by district (and cluster, where available). |
| **Cleaned Response Data** | Excel | The full response dataset with applied geocodes and match metadata columns. |
| **Settlement Shapefile** | ESRI Shapefile (zipped) | Point layer for GIS software. |
| **GeoPackage** | `.gpkg` | Same data, modern GIS format. |
| **GeoJSON** | `.geojson` | Web-GIS-friendly point layer. |
| **QA Excel Report** | Excel | Readiness metrics, validation issues, full match table, a dedicated "Low Confidence" sheet, and district/cluster summaries. |
| **QA / Matching Report** | PDF | A shareable summary of matching results and data quality, suitable for a partner or coordination meeting. |
| **Audit Log (CSV)** | CSV | Every score component, the automatic decision, and any human review decision, reviewer, and note — one row per matched record. |
| **Audit Log (Excel)** | Excel | Same audit trail as the CSV, in workbook form. |

A processing log (`ocha_processing_log.txt`) and a combined **Download All Outputs** ZIP are generated automatically alongside your selected files. Individual files remain available for one-off download under **Individual files**. Each output card shows **Ready** once generated, or an error message if a stage failed (for example, if GeoPandas isn't installed for the GIS exports).

![Outputs generated and ready to download, including the new audit log](images/05_outputs.png)

---

## 9a. Place Intelligence Database: Backup & Import

The app learns as you review: accepted matches become approved aliases, and rejections are remembered too, both stored locally in `data/place_intelligence.db`. A panel at the bottom of the dashboard lets you manage that history directly:

- **Export Approved Aliases / Review History / Rejected Matches** — CSV downloads of each table.
- **Backup Full Database** — a complete copy of the raw database file.
- **Import** — upload a CSV/Excel alias list or a previous `.db` backup. Files are validated before anything is written, and imports merge with existing history (increasing approval counts on a repeat match) rather than silently overwriting it.

**Hosted deployments:** unless the hosting platform provides persistent storage, this database resets on every restart/redeploy. Export a backup regularly if you're relying on accumulated alias history in a hosted instance.

![Place Intelligence Database panel with export and import controls](images/06_database.png)

---

## 10. Reading the sidebar at a glance

The sidebar's **Information** panel is a live dashboard of where you stand:

- **Total Records** — rows in the response file.
- **Records with GPS** — already had valid coordinates on upload.
- **Missing GPS** — still need matching.
- **Matched** — auto-matched + needs-review records combined.
- **Needs Review** — subset of Matched that isn't yet at auto-accept confidence.
- **Processed** — rows in the final processed dataset (used for outputs/map) after geocodes are applied.

The **Reference Data** section above it reminds you which gazetteer and boundary files are currently loaded.

---

## 11. Troubleshooting / FAQ

**"sentence-transformers is not installed" warning.**
Semantic matching was turned on but the package isn't available in this environment. The run still completes using RapidFuzz only. Ask whoever manages the installation to run `pip install sentence-transformers`, then try again.

**"Ollama is not reachable at localhost:11434" warning.**
Ollama reasoning notes were turned on, but no local Ollama server is running. The run still completes without the extra reasoning notes. To enable it: install [Ollama](https://ollama.com), run `ollama pull qwen2.5`, then `ollama serve`, and re-run matching.

**A settlement I know exists isn't matching at all.**
Check it's actually present in the gazetteer (correct spelling, correct district). If it's genuinely missing from the gazetteer, no amount of fuzzy or semantic matching will find it — it needs to be added to the gazetteer file, or the coordinate entered manually.

**The map shows fewer points than my total record count.**
The map only plots rows that currently have a valid coordinate. Rows still "Needs Review" or "Unmatched" won't appear until they're resolved (Step 4) and geocodes are applied.

**I want to start over with a different dataset.**
Click **Restart Process** in the sidebar. This clears loaded files, matches, and any generated outputs, without needing to reload the app.

**Is any of my data leaving this computer?**
No. The app has no cloud dependency for its core matching (RapidFuzz and Sentence Transformers both run locally), and Ollama, if used, is also a local process. The header's **Local Mode** badge is a permanent reminder of this.

**A match shows a high score but still landed in Needs Review.**
One of the hard safeguards tripped — a district/region contradiction, an ambiguous name with no way to disambiguate it, excessive spatial distance, near-tied top candidates, a history of rejection for this exact context, or missing gazetteer metadata. Check Compare Candidates (Step 4) to see why; the safeguard is listed in the row's Reason text.

---

## 12. Quick reference

**Confidence thresholds**

| Range | Status |
|---|---|
| 90–100% | Auto Matched |
| 85–89.99% | Needs Review |
| Below 85% | Unmatched |

**Status colors used throughout the app (table pills and map markers)**

| Color | Status |
|---|---|
| 🟢 Green | Auto-accepted / already geocoded on upload |
| 🟠 Amber | Needs review |
| 🔴 Red | Unresolved / invalid |
| ⚪ Grey | Manually edited / rejected |

**Required columns**

| Dataset | Required fields |
|---|---|
| Response data | Settlement, District |
| Gazetteer | Settlement, District, Latitude, Longitude |
