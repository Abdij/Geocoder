---
title: Settlement Matching and Geocoding Tool
emoji: 🌍
colorFrom: blue
colorTo: green
sdk: streamlit
app_file: app.py
pinned: false
---

# Settlement Matching and Geocoding Tool

Local, human-in-the-loop humanitarian GIS processing for settlement response data. The app runs on a Windows workstation (or as a standalone desktop install, or hosted) with Streamlit and open-source Python libraries.

Most of the matching in this tool is **deterministic and rule-based** (exact lookups, RapidFuzz string similarity, GIS spatial checks). Two pieces are **machine-learning-assisted** (Sentence Transformer embeddings, used only to re-rank a short deterministic shortlist) and **local-LLM-assisted** (an optional Ollama note that explains a suggestion in plain language). None of the three ever auto-decides anything on their own — a human always reviews anything below the auto-accept bar, and hard safety rules block auto-acceptance outright in several situations regardless of confidence score. This is not a "fully AI-driven" tool; it's a GIS/data-quality tool with optional, clearly-bounded AI assistance.

## What It Does

- Loads partner response spreadsheets, settlement gazetteers, and district boundary layers.
- Validates missing GPS values, duplicates, invalid coordinates, missing settlements, missing districts, and administrative hierarchy issues.
- Matches records missing coordinates against the gazetteer using a layered pipeline: analyst-approved aliases first, then exact matches, then RapidFuzz fuzzy matching, then optional semantic re-ranking — see [Layered Matching Workflow](#layered-matching-workflow).
- Scores every candidate on name, district, region, spatial, historical, and semantic evidence, combined into one transparent composite confidence score — see [Composite Confidence Scoring](#composite-confidence-scoring).
- Learns from analyst decisions: an accepted match becomes an approved alias for next time; a rejected candidate is remembered so it isn't suggested with the same confidence again — see [Alias and Historical Learning](#alias-and-historical-learning).
- Never auto-accepts a match with a district/region contradiction, an unresolvable ambiguous name, excessive spatial distance, near-tied candidates, or a history of rejection for that exact context, no matter how high the raw confidence score is — see [Hard Auto-Acceptance Safeguards](#hard-auto-acceptance-safeguards).
- Lets a reviewer compare the top-5 candidates side by side, not just accept/reject the single top guess — see [Candidate Comparison](#candidate-comparison).
- Keeps a human review table for uncertain matches, with map-assisted context (submitted-to-candidate lines, distance labels, conflict markers).
- Generates cleaned Excel workbooks, district response worksheets, GeoPackage, Shapefile ZIP, GeoJSON, QA Excel, QA PDF, a processing log, and a full audit trail (CSV + Excel) — see [Audit Logs](#audit-logs).

## Install

```powershell
cd OCHA_Settlement_Response_Processor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

GeoPandas, Fiona, and Pyogrio depend on native geospatial wheels. If installation is difficult on a locked-down workstation, install from conda-forge:

```powershell
conda create -n ocha_processor python=3.11 streamlit pandas numpy openpyxl geopandas shapely pyogrio fiona rapidfuzz folium reportlab requests geopy -c conda-forge
conda activate ocha_processor
pip install streamlit-folium sentence-transformers pytest
```

The local alias/review database uses Python's built-in `sqlite3` module — no separate database server or extra dependency required.

## Run

```powershell
streamlit run app.py
```

Then use the left navigation:

1. Upload response data, gazetteer, and optional boundaries.
2. Review validation indicators.
3. Run settlement matching.
4. Compare candidates, accept, reject, or edit suggestions.
5. Generate and download outputs (including the audit trail).

## Deploy to Hugging Face Spaces

The YAML block at the top of this README is a Hugging Face Spaces config — the repo can be pushed directly as a Space.

1. Create a new Space at huggingface.co/new-space with SDK set to **Streamlit**.
2. Add it as a git remote and push this repo:

   ```powershell
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space main
   ```

3. The Space installs `requirements.txt` automatically and launches `app.py`. No Dockerfile is needed — GeoPandas, Fiona, and Pyogrio ship prebuilt Linux wheels that install with plain `pip`.
4. Free-tier Spaces give 16 GB RAM, which comfortably fits Sentence Transformers + GeoPandas (Streamlit Community Cloud's free tier, at ~1 GB, does not). Ollama still cannot run here — there is no way to keep a local daemon alive on a free Space, so leave "Enable Ollama reasoning notes" off in a hosted deployment, or swap it for a hosted LLM API (e.g. Gemini, Groq) called over HTTPS instead of `localhost:11434`.
5. Free Spaces are public by default; a private Space requires a paid plan.
6. **Warn users that public hosted deployments should not contain confidential humanitarian datasets.** A public Space is visible to anyone with the URL; use a private Space (paid) or the local/desktop install for sensitive response data.
7. See [Local versus Hosted Behavior](#local-versus-hosted-behavior) for how the alias/review database behaves differently between a persistent local install and an ephemeral hosted instance.

## Sample Data

The `data` folder includes:

- `sample_response.csv`
- `sample_settlement_gazetteer.csv`
- `sample_district_boundaries.geojson`

Open the app and click `Load Sample Data` to test the full workflow.

## Expected Columns

The app detects common humanitarian column names automatically.

Response data should include settlement and district fields. Latitude and longitude are optional because missing coordinates are matched.

Gazetteer data should include settlement, district, latitude, and longitude. Region is recommended. An ID column (`gazetteer_id`, `settlement_id`, `p_code`, `pcode`, `gid`, etc.) is optional — if present it's kept as-is; if absent, a stable ID is generated deterministically from the normalized settlement/district/region and rounded coordinates, never from the row's position in the file. See [Gazetteer IDs](#gazetteer-ids).

Optional response fields such as partner, cluster, beneficiaries, activity, and month are preserved in exports and used in summary workbooks when present.

## Layered Matching Workflow

Each record needing a coordinate goes through search tiers in order, stopping at the first tier that produces a usable result:

1. **Approved alias match** — a prior analyst decision for this exact (normalized name, district, region) combination, if one exists.
2. **Exact settlement + district + region** match.
3. **Exact settlement + district** match (region unknown or different).
4. **Exact settlement + region** match (district unknown or different).
5. **Unique national exact settlement match** — only trusted when the name resolves to exactly one gazetteer row nationally; if the same name exists in more than one district and there's no district/region evidence to disambiguate, this tier deliberately refuses to guess (see [Hard Auto-Acceptance Safeguards](#hard-auto-acceptance-safeguards)).
6. **District-constrained fuzzy search** (RapidFuzz), then **region-constrained**, then **national fallback** if narrower tiers find nothing.
7. **Optional semantic re-ranking** — if Sentence Transformers is enabled, re-ranks the fuzzy shortlist by embedding similarity rather than comparing the query against the entire gazetteer (keeps it fast on large files).

The pipeline always returns the top 5 ranked candidates, not just the first match found — the [Candidate Comparison](#candidate-comparison) panel lets a reviewer see all of them.

Fuzzy name scoring combines four RapidFuzz metrics — `ratio` (20%), `WRatio` (35%), `token_sort_ratio` (20%), `token_set_ratio` (25%) — into one score, so word-order differences and dropped descriptive words (e.g. a missing "IDP Camp" suffix) don't tank the match the way plain `ratio` alone would.

## Gazetteer IDs

Matching results, review decisions, approved aliases, rejection records, and GIS exports all key off a stable `gazetteer_id`, not a DataFrame row number (which shifts if the gazetteer is re-uploaded, re-sorted, or edited). If the uploaded gazetteer has no ID column, one is generated deterministically from the normalized settlement/district/region plus coordinates rounded to 5 decimal places — the same input always produces the same ID, and two different settlements never collide.

## Alias and Historical Learning

A local SQLite database at `data/place_intelligence.db` (created automatically on first use) stores:

- **`approved_aliases`** — every settlement name variant an analyst has confirmed maps to a specific gazetteer entry, with an approval count and timestamps. Only ever written when an analyst explicitly accepts a match (including picking a different candidate from the comparison panel) — never from a raw, unreviewed model suggestion.
- **`review_decisions`** — an immutable log of every accept/reject decision, preserving prior decisions rather than overwriting them.
- **`rejected_candidates`** — how many times a specific (submitted context → candidate) pairing has been rejected, used as a confidence penalty and a hard auto-accept block after repeated rejections.

Re-saving an unchanged review (e.g. clicking "Save Reviewed Matches" twice without changing anything) is a no-op — it doesn't inflate approval counts or duplicate history.

## Candidate Comparison

The Settlement Matching panel's "Compare Candidates" section lets a reviewer pick any record still needing review and see its full ranked shortlist side by side: settlement, district, region, name/semantic/spatial/historical scores, distance from the submitted point, and any admin conflict flag. "Use This Candidate" swaps the suggestion to a different one from the list and marks the row accepted — the analyst's explicit choice, not the pipeline's original guess, is what gets applied and taught back to the alias table.

## Spatial Validation

When a submitted coordinate exists (only for *invalid*, not merely missing, GPS values — a missing value never had a coordinate to validate), the pipeline computes:

- Distance in km between the submitted and candidate coordinates (geodesic via geopy when available, haversine fallback otherwise), scored 100/90/70/40/0 across the 0–2/2–5/5–15/15–30/>30 km bands.
- Whether the submitted coordinate looks like it has latitude/longitude swapped (in-range as given but only valid for Somalia after swapping).
- Whether the submitted coordinate is nowhere near Somalia at all (coarse bounding-box check).
- Whether a point falls within a named district boundary, when a boundary layer was uploaded — this degrades to "unavailable," not "false," when no boundary layer exists, so missing evidence is never scored as a conflict.

The map's review layer draws a line from the submitted point to the suggested candidate with a distance tooltip, and gives a flagged admin/spatial conflict a distinct dashed marker ring.

## Composite Confidence Scoring

Every match gets one transparent `overall_confidence` score built from up to six components:

- Name similarity: 35%
- District consistency: 20%
- Region consistency: 10%
- Spatial consistency: 15%
- Historical evidence: 10%
- Semantic similarity: 10%

If a component is unavailable (e.g. no submitted coordinate, so no spatial score; no semantic matching enabled, so no semantic score), its weight is redistributed proportionally across whatever components **are** available — missing evidence is never scored as either positive or negative. A prior-rejection penalty (15 points per repeat rejection of the exact same candidate, capped at 30) is subtracted afterward. Every component score, plus a plain-language explanation of how the number was derived, is available in the matching results and the audit export.

Historical evidence itself is tiered from prior analyst approvals: 5+ approvals is strong (100), 2–4 is moderate (70), 1 is weak (40), and 0 is *unavailable* (not a low score — "never reviewed before" isn't evidence against a candidate). A fixed decay applies if the most recent approval is roughly 2+ years old, since gazetteer and naming conventions can drift over that time.

**Thresholds** (raised from 90/75 to 95/85 as part of this upgrade — see [Migration Notes](#migration-notes)):

- 95–100%: auto-accepted (subject to the hard safeguards below)
- 85–94.99%: needs review
- Below 85%: unresolved

## Hard Auto-Acceptance Safeguards

A record is **never** auto-accepted, regardless of confidence score, when any of these hold:

- The candidate's district or region is a genuine contradiction (not just unknown).
- The settlement name exists in more than one district nationally and there's no district/region/coordinate evidence to disambiguate it.
- Spatial distance between submitted and candidate coordinates exceeds 15 km.
- The top two candidates are within 5 confidence points of each other (the ambiguity margin).
- The candidate has been rejected 2+ times before for this exact submitted context.
- The candidate is missing both district and region metadata in the gazetteer.

A blocked record still lands in "needs review" rather than "unresolved" if its confidence clears that lower bar — blocking only removes the auto-accept path, it doesn't make the candidate look worse to a reviewer.

## Optional Local AI

The app works offline without cloud APIs. Two optional local AI steps can be turned on from toggles in the Settlement Matching panel, right above the "Run Settlement Matching" button:

- **Semantic matching (Sentence Transformers)** — embeds settlement names and re-ranks the RapidFuzz shortlist by embedding similarity, rather than comparing every response record against the whole gazetteer.
- **Ollama reasoning notes** — for matches that land in "needs review", asks a local Qwen model for a short (<40 word) note explaining the most plausible candidate, given the same score evidence the pipeline computed (name/semantic scores, distance, prior approval/rejection counts, admin conflicts). The prompt explicitly forbids inventing a settlement or coordinate not in the candidate list, and the note is advisory only — it never changes the selected candidate, confidence score, or decision status.

Both are off by default. Matching always falls back to exact matching + RapidFuzz fuzzy matching if a toggle is on but its dependency isn't available — this is verified directly in the test suite (a simulated model failure falls back to fuzzy without crashing or leaving stale scores behind).

### Enabling semantic matching

Install Sentence Transformers into the app's environment:

```powershell
pip install sentence-transformers
```

Then check "Enable semantic matching with Sentence Transformers" in the Settlement Matching panel before running matching. The first run downloads the `all-MiniLM-L6-v2` model, which can take a moment; if the package isn't installed, the app shows a warning and continues with RapidFuzz only.

### Enabling Ollama reasoning notes

1. Install Ollama from [ollama.com](https://ollama.com) and pull a Qwen model:

   ```powershell
   ollama pull qwen2.5
   ```

2. Start the Ollama server before (or while) running the app:

   ```powershell
   ollama serve
   ```

3. In the Settlement Matching panel, check "Enable Ollama reasoning notes" before running matching.

If Ollama isn't reachable at `localhost:11434` when matching runs, the app shows a warning and skips reasoning notes for that run rather than failing.

## Audit Logs

The Outputs panel includes two additional selectable outputs, **Audit Log (CSV)** and **Audit Log (Excel)**, combining every automated score component with whatever human review decision (if any) has since been recorded for each record: run ID, timestamp, original and normalized settlement, suggested and final gazetteer match, every score component, overall confidence, matching method, whether semantic/Ollama models were available for that run, the automatic decision, the human decision, reviewer, and reviewer note. Like every other export, it's written via the app's `output_path()` helper, which never overwrites a prior export or an uploaded file — each run gets its own auto-numbered filename.

## Database Backup

The "Place Intelligence Database — Backup & Import" panel at the bottom of the dashboard lets you:

- Export approved aliases, review history, or rejected matches as CSV.
- Download a full backup of the raw SQLite database file.
- Import a CSV/Excel alias list (validated for required columns before anything is written) or a full `.db` backup from another machine — both merge into existing history via the same upsert path a normal analyst approval takes, so approval counts combine correctly instead of being silently overwritten or duplicated.

## Local versus Hosted Behavior

- **Local/desktop install**: `data/place_intelligence.db` persists on disk between sessions — the alias/review history genuinely accumulates over time, which is the whole point of the learning workflow.
- **Hosted (Railway, Hugging Face Spaces, etc.)**: unless the platform provides persistent storage, the database resets whenever the instance restarts or redeploys. Use the backup/export controls regularly if you rely on accumulated alias history in a hosted deployment, and see the warning above about not hosting confidential data on a public Space.
- Ollama reasoning notes require a local daemon reachable at `localhost:11434` and cannot run on most hosted platforms — see [Deploy to Hugging Face Spaces](#deploy-to-hugging-face-spaces) for a hosted-LLM-API alternative.

## Known Limitations

- **Region boundaries**: the app supports uploading district boundaries for spatial containment checks, but there's no region-boundary upload path today, so region-level containment (as opposed to region *name* consistency scoring) isn't available.
- **Performance on very large files**: the layered candidate generator re-filters the gazetteer per record rather than reusing the old per-district/per-query result cache the previous single-tier matcher had. This is a reasonable trade-off for correctness and transparency on typical humanitarian response files (hundreds to low thousands of rows); very large files (tens of thousands+) may run noticeably slower than the pre-upgrade matcher.
- **Semantic re-ranking scope**: it only re-ranks the RapidFuzz shortlist (default top 8), not the full gazetteer — this keeps it fast but means an extremely poor fuzzy shortlist won't be rescued by semantic similarity alone.
- **Ollama notes are advisory-only by design**: they can help a reviewer decide faster but never change confidence, status, or the selected candidate automatically.

## Architecture

```text
app.py
config.py
backend/
  load_data.py
  validate_data.py
  text_normalizer.py
  candidate_generator.py
  spatial_matcher.py
  confidence_scorer.py
  alias_repository.py
  review_repository.py
  audit_logger.py
  db_backup.py
  llm_reviewer.py
  settlement_matcher.py
  geocoder.py
  district_summary.py
  gis_exporter.py
  excel_exporter.py
  qa_report.py
  map_generator.py
  utils.py
frontend/
  dashboard_page.py        (the live single-page app)
  upload_page.py            (legacy, not called by app.py)
  validation_page.py        (legacy, not called by app.py)
  matching_page.py          (legacy, not called by app.py)
  review_page.py            (legacy, not called by app.py)
  outputs_page.py           (legacy, not called by app.py)
tests/
assets/
data/
  place_intelligence.db     (created automatically, not committed to git)
uploads/
outputs/
```

`app.py` renders only `frontend/dashboard_page.py` — the other `frontend/*_page.py` files are an earlier multi-page architecture that predates the current single-page dashboard and are not wired into the live app. They're left in place but not maintained; don't assume changes to `dashboard_page.py` are reflected there.

The code is modular so later integrations can add ActivityInfo APIs, ArcGIS Online publishing, ArcGIS Enterprise publishing, Power BI exports, dashboard generation, and further AI-assisted narrative generation without rewriting the core local processors.

## Tests

```powershell
pip install pytest
pytest tests/
```

The suite covers text normalization, gazetteer ID generation/stability, SQLite persistence (aliases, review decisions, rejections), spatial validation, historical/composite confidence scoring, hard safety constraints, the layered candidate generator (including the transliteration pairs Baydhabo→Baidoa, Mogadisho/Muqdishu→Muqdisho, Johwar→Jowhar, Beledweyne→Belet Weyne, Xudur→Hudur, and ambiguous same-name-different-district cases), semantic re-ranking and fallback, the Ollama prompt builder, the analyst learning workflow, map generation, audit export, and database backup/import — all running against synthetic data or in-memory/temp-file databases, none touching the real `data/place_intelligence.db`.

## Migration Notes

This upgrade (the "Humanitarian Place Intelligence Engine" work) is additive wherever practical. Existing workflows continue to work with `streamlit run app.py`, and the app runs correctly with only exact matching + RapidFuzz if Sentence Transformers isn't installed, and without Ollama running.

**New files**: `backend/text_normalizer.py`, `backend/candidate_generator.py`, `backend/spatial_matcher.py`, `backend/confidence_scorer.py`, `backend/alias_repository.py`, `backend/review_repository.py`, `backend/audit_logger.py`, `backend/db_backup.py`, `backend/llm_reviewer.py`, `tests/` (15 test files).

**Modified files**: `backend/settlement_matcher.py` (the matching pipeline was rewritten internally; its public `match_records()` now returns `(matches_df, candidates_by_record)` instead of just `matches_df` — the one live call site in `frontend/dashboard_page.py` was updated, along with the orphaned `frontend/matching_page.py` for consistency), `backend/geocoder.py` (writes analyst decisions to the database), `backend/map_generator.py` (submitted-coordinate lines and conflict markers), `backend/utils.py` (`generate_gazetteer_id`/`ensure_gazetteer_ids`), `config.py` (new thresholds and `gazetteer_id` column alias), `frontend/dashboard_page.py` (candidate comparison panel, audit outputs, database management panel), `requirements.txt` (added `geopy`, `pytest`).

**Database initialization**: `data/place_intelligence.db` is created automatically (schema included) the first time any matching or review action needs it — no manual migration step. It's git-ignored, same as `uploads/`/`outputs/`.

**Compatibility**: `MATCH_COLUMNS` keeps every legacy field name (`latitude`, `longitude`, `status`, `confidence`, `suggested_district`, `suggested_region`, `accept`, `reject`, etc.) fully populated with its original meaning; the Phase-12 expanded schema fields (`overall_confidence`, `name_score`, `distance_km`, `candidate_rank`, `decision_status`, `llm_note`, etc.) are added alongside them, not instead of them, so the existing exporters and review UI needed no changes to their column expectations.

**Changed confidence thresholds**: auto-accept raised from 90% to 95%, needs-review floor raised from 75% to 85%. This is deliberate, not a bug — the layered candidate generator and the hard safety gates now carry more of the acceptance burden than the old single fixed-weight formula did, so the confidence bar itself is stricter. A match that would have auto-accepted at 93% under the old thresholds now correctly lands in needs-review.

**Sentence Transformers fallback plan**: if the package isn't installed, `use_semantic` is forced off in the UI, `generate_candidates()` never receives a model, and matching proceeds through the exact/RapidFuzz tiers only — verified directly in the test suite with a simulated model-import failure.

**Test commands**: `pytest tests/` (150 tests at the time of this upgrade, all passing, all self-contained against synthetic data / in-memory or temp-file databases).
