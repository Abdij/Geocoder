---
title: OCHA Settlement Response Processor
emoji: 🌍
colorFrom: blue
colorTo: green
sdk: streamlit
app_file: app.py
pinned: false
---

# OCHA Settlement Response Processor

Local AI-assisted humanitarian GIS processing for settlement response data. The app runs on a Windows workstation with Streamlit and open-source Python libraries.

## What It Does

- Loads partner response spreadsheets, settlement gazetteers, and district boundary layers.
- Validates missing GPS values, duplicates, invalid coordinates, missing settlements, missing districts, and administrative hierarchy issues.
- Matches records missing coordinates against the gazetteer using exact matching, RapidFuzz, optional Sentence Transformers, and optional local Ollama reasoning.
- Keeps a human review table for uncertain matches.
- Generates cleaned Excel workbooks, district response worksheets, GeoPackage, Shapefile ZIP, GeoJSON, QA Excel, QA PDF, and a processing log.

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
conda create -n ocha_processor python=3.11 streamlit pandas numpy openpyxl geopandas shapely pyogrio fiona rapidfuzz folium reportlab requests -c conda-forge
conda activate ocha_processor
pip install streamlit-folium sentence-transformers
```

## Run

```powershell
streamlit run app.py
```

Then use the left navigation:

1. Upload response data, gazetteer, and optional boundaries.
2. Review validation indicators.
3. Run settlement matching.
4. Accept, reject, or edit suggestions.
5. Generate and download outputs.

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

## Sample Data

The `data` folder includes:

- `sample_response.csv`
- `sample_settlement_gazetteer.csv`
- `sample_district_boundaries.geojson`

Open the app and click `Load Sample Data` to test the full workflow.

## Expected Columns

The app detects common humanitarian column names automatically.

Response data should include settlement and district fields. Latitude and longitude are optional because missing coordinates are matched.

Gazetteer data should include settlement, district, latitude, and longitude. Region is recommended.

Optional response fields such as partner, cluster, beneficiaries, activity, and month are preserved in exports and used in summary workbooks when present.

## Matching Confidence

The confidence model uses:

- Settlement similarity: 50%
- District similarity: 25%
- Region similarity: 15%
- Administrative consistency: 10%

Thresholds:

- 90-100%: automatically accepted
- 75-89%: needs review
- Below 75%: unresolved

## Optional Local AI

The app works offline without cloud APIs. Two optional local AI steps can be turned on from toggles in the Settlement Matching panel, right above the "Run Settlement Matching" button:

- **Semantic matching (Sentence Transformers)** — embeds settlement names and picks the closest match by embedding similarity, on top of the default RapidFuzz matching.
- **Ollama reasoning notes** — for matches that land in "needs review", asks a local Ollama model for a short (<25 word) note explaining the suggested match.

Both are off by default. Matching always falls back to exact matching + RapidFuzz fuzzy matching if a toggle is on but its dependency isn't available.

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

## Architecture

```text
app.py
config.py
backend/
  load_data.py
  validate_data.py
  settlement_matcher.py
  geocoder.py
  district_summary.py
  gis_exporter.py
  excel_exporter.py
  qa_report.py
  map_generator.py
frontend/
  upload_page.py
  validation_page.py
  matching_page.py
  review_page.py
  outputs_page.py
assets/
data/
uploads/
outputs/
```

The code is modular so later integrations can add ActivityInfo APIs, ArcGIS Online publishing, ArcGIS Enterprise publishing, Power BI exports, dashboard generation, and AI narrative generation without rewriting the core local processors.
