from pathlib import Path


APP_NAME = "Settlement Matching and Geocoding Tool"
APP_TAGLINE = "Local AI-assisted humanitarian GIS processing for settlement response data"

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"
STATIC_DIR = BASE_DIR / "static"

for directory in (ASSETS_DIR, DATA_DIR, UPLOADS_DIR, OUTPUTS_DIR, STATIC_DIR):
    directory.mkdir(parents=True, exist_ok=True)

PLACE_INTELLIGENCE_DB_PATH = DATA_DIR / "place_intelligence.db"

DEFAULT_CRS = "EPSG:4326"
PROJECTED_CRS = "EPSG:3857"

# MATCH_AUTO_ACCEPT was raised to 95 as part of the Place Intelligence Engine
# upgrade on the assumption that spatial evidence would often be available to
# help clear the bar. In practice, match_records() only ever runs on records
# that are missing/invalid on coordinates by definition, so spatial evidence
# is never available at auto-accept time - even a perfect name/district/region
# match tops out around 92-93% once spatial and historical evidence are
# absent, permanently short of 95. Reverted to the original 90 so records
# with strong available evidence can actually clear the auto-accept bar; the
# hard safety gates in confidence_scorer.determine_match_status()
# (contradictions, ambiguous names, distance, repeated rejections) still
# block anything risky regardless of this threshold.
MATCH_AUTO_ACCEPT = 90
MATCH_NEEDS_REVIEW = 85
AMBIGUITY_MARGIN = 5
MAX_AUTO_ACCEPT_DISTANCE_KM = 15
REPEATED_REJECTION_BLOCK_THRESHOLD = 2

SUPPORTED_TABLE_EXTENSIONS = {".csv", ".xlsx", ".xls"}
SUPPORTED_SPATIAL_EXTENSIONS = {".geojson", ".json", ".gpkg", ".shp", ".zip"}

COLUMN_ALIASES = {
    "settlement": [
        "settlement",
        "settlement_name",
        "settlement name",
        "village",
        "village_name",
        "site",
        "site_name",
        "location",
        "location_name",
        "town",
    ],
    "district": [
        "district",
        "district_name",
        "district name",
        "admin2",
        "admin2_name",
        "adm2",
        "adm2_en",
    ],
    "region": [
        "region",
        "region_name",
        "region name",
        "admin1",
        "admin1_name",
        "adm1",
        "adm1_en",
    ],
    "latitude": [
        "latitude",
        "lat",
        "y",
        "gps_latitude",
        "gps latitude",
        "y_coord",
        "y coordinate",
    ],
    "longitude": [
        "longitude",
        "lon",
        "long",
        "lng",
        "x",
        "gps_longitude",
        "gps longitude",
        "x_coord",
        "x coordinate",
    ],
    "cluster": [
        "cluster",
        "sector",
        "activity_cluster",
        "response_cluster",
    ],
    "partner": [
        "partner",
        "organization",
        "organisation",
        "implementing_partner",
        "implementing partner",
        "agency",
    ],
    "beneficiaries": [
        "beneficiaries",
        "people_reached",
        "people reached",
        "reached",
        "individuals",
        "population",
        "total_beneficiaries",
    ],
    "gazetteer_id": [
        "gazetteer_id",
        "gazetteer id",
        "settlement_id",
        "settlement id",
        "place_id",
        "place id",
        "p_code",
        "pcode",
        "gid",
    ],
}

REQUIRED_RESPONSE_FIELDS = ["settlement", "district"]
REQUIRED_GAZETTEER_FIELDS = ["settlement", "district", "latitude", "longitude"]

# Matched by substring (see excel_exporter._cluster_color), not exact
# equality, since real response data rarely uses the bare cluster name
# ("Food Security Cluster", "Shelter and NFIs", "Gender Based Violence" all
# need to resolve). Protection's Areas of Responsibility (Child Protection,
# GBV, HLP, Mine Action) share Protection's color rather than getting their
# own, since they're sub-clusters of it, not independent clusters. Ordered
# longest-key-first isn't required here since every key maps to a distinct
# color family, but child/gbv/hlp are listed close to "protection" to make
# that relationship obvious when this dict is edited.
CLUSTER_COLORS = {
    "cccm": "5B9BD5",
    "education": "70AD47",
    "food security": "FFC000",
    "health": "ED7D31",
    "nutrition": "A64D79",
    "protection": "7030A0",
    "child protection": "7030A0",
    "gender based violence": "7030A0",
    "gbv": "7030A0",
    "hlp": "7030A0",
    "mine action": "7030A0",
    "shelter": "4472C4",
    "wash": "00A6A6",
}

STATUS_COLORS = {
    "auto_accepted": "#107C10",
    "accepted": "#107C10",
    "needs_review": "#FFB900",
    "manual_review": "#FFB900",
    "unresolved": "#C50F1F",
    "rejected": "#605E5C",
    "already_geocoded": "#0078D4",
}

SAMPLE_RESPONSE = DATA_DIR / "sample_response.csv"
SAMPLE_GAZETTEER = DATA_DIR / "sample_settlement_gazetteer.csv"
SAMPLE_BOUNDARIES = DATA_DIR / "sample_district_boundaries.geojson"
