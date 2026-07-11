from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from config import COLUMN_ALIASES, OUTPUTS_DIR


def normalize_text(value: Any) -> str:
    """Normalize names for matching while preserving Somali place-name intent."""
    if pd.isna(value):
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"[\s_-]+", " ", text).strip()
    return text


def normalize_column_name(value: Any) -> str:
    return normalize_text(value).replace(" ", "_")


def detect_column_map(df: pd.DataFrame | None) -> dict[str, str | None]:
    """Map semantic field names to actual dataframe columns using aliases."""
    if df is None or df.empty:
        return {field: None for field in COLUMN_ALIASES}

    normalized_lookup = {normalize_column_name(column): column for column in df.columns}
    column_map: dict[str, str | None] = {}

    for field, aliases in COLUMN_ALIASES.items():
        found = None
        for alias in aliases:
            key = normalize_column_name(alias)
            if key in normalized_lookup:
                found = normalized_lookup[key]
                break
        if found is None:
            # Fuzzy fallback for common exports such as "Settlement / Site Name".
            for normalized_column, original_column in normalized_lookup.items():
                if any(normalize_column_name(alias) in normalized_column for alias in aliases):
                    found = original_column
                    break
        column_map[field] = found

    return column_map


def missing_required_fields(column_map: dict[str, str | None], required: Iterable[str]) -> list[str]:
    return [field for field in required if not column_map.get(field)]


def generate_gazetteer_id(
    settlement: Any,
    district: Any,
    region: Any,
    latitude: Any,
    longitude: Any,
) -> str:
    """Deterministically derive a stable gazetteer ID from a candidate's identity.

    Used when an uploaded gazetteer has no ID column of its own, so matches,
    review decisions, aliases, and exports can reference a stable key instead
    of a DataFrame row number (which shifts if rows are re-ordered or the
    gazetteer is re-uploaded).
    """
    from backend.text_normalizer import normalize_place_name

    settlement_norm = normalize_place_name(settlement)
    district_norm = normalize_place_name(district)
    region_norm = normalize_place_name(region)

    try:
        lat_key = f"{round(float(latitude), 5):.5f}"
    except (TypeError, ValueError):
        lat_key = ""
    try:
        lon_key = f"{round(float(longitude), 5):.5f}"
    except (TypeError, ValueError):
        lon_key = ""

    key = f"{settlement_norm}|{district_norm}|{region_norm}|{lat_key}|{lon_key}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"gaz_{digest}"


def ensure_gazetteer_ids(gazetteer_df: pd.DataFrame, column_map: dict[str, str | None] | None = None) -> pd.DataFrame:
    """Return a copy of the gazetteer with a stable "gazetteer_id" column.

    If the upload already has an ID column (detected via the "gazetteer_id"
    alias group), rows with a blank value are backfilled with a generated ID
    rather than replacing existing IDs, so partner-provided codes are kept.
    """
    if gazetteer_df is None or gazetteer_df.empty:
        return gazetteer_df

    df = gazetteer_df.copy()
    columns = column_map if column_map is not None else detect_column_map(df)
    settlement_col = columns.get("settlement")
    district_col = columns.get("district")
    region_col = columns.get("region")
    lat_col = columns.get("latitude")
    lon_col = columns.get("longitude")
    id_col = columns.get("gazetteer_id")

    if id_col and id_col != "gazetteer_id":
        df = df.rename(columns={id_col: "gazetteer_id"})
    elif not id_col:
        df["gazetteer_id"] = ""

    missing_mask = df["gazetteer_id"].isna() | (df["gazetteer_id"].astype(str).str.strip() == "")
    if missing_mask.any():
        df.loc[missing_mask, "gazetteer_id"] = df.loc[missing_mask].apply(
            lambda row: generate_gazetteer_id(
                row.get(settlement_col) if settlement_col else None,
                row.get(district_col) if district_col else None,
                row.get(region_col) if region_col else None,
                row.get(lat_col) if lat_col else None,
                row.get(lon_col) if lon_col else None,
            ),
            axis=1,
        )

    return df


def coerce_numeric(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(series, errors="coerce")


def coordinate_masks(
    df: pd.DataFrame,
    latitude_col: str | None,
    longitude_col: str | None,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return missing, invalid, and valid coordinate masks."""
    index = df.index
    if not latitude_col or not longitude_col:
        missing = pd.Series(True, index=index)
        invalid = pd.Series(False, index=index)
        valid = pd.Series(False, index=index)
        return missing, invalid, valid

    lat = coerce_numeric(df[latitude_col])
    lon = coerce_numeric(df[longitude_col])
    missing = lat.isna() | lon.isna()
    invalid_range = (~lat.between(-90, 90)) | (~lon.between(-180, 180))
    invalid = (~missing) & invalid_range
    valid = (~missing) & (~invalid_range)
    return missing, invalid, valid


def safe_percent(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def traffic_light(value: float, green_at: float, yellow_at: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        if value >= green_at:
            return "green"
        if value >= yellow_at:
            return "yellow"
        return "red"
    if value <= green_at:
        return "green"
    if value <= yellow_at:
        return "yellow"
    return "red"


def safe_slug(value: Any, fallback: str = "item") -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or fallback


def unique_path(path: Path) -> Path:
    path = Path(path)
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def output_path(filename: str) -> Path:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return unique_path(OUTPUTS_DIR / filename)


def human_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}K"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.1f}"


def format_error(error: Exception) -> str:
    return f"{error.__class__.__name__}: {error}"


@contextmanager
def timed_operation(label: str, log: list[str] | None = None):
    start = time.perf_counter()
    if log is not None:
        log.append(f"Started {label}")
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if log is not None:
            log.append(f"Completed {label} in {elapsed:.2f}s")


def truncate_sheet_name(name: Any, existing: set[str] | None = None) -> str:
    existing = existing if existing is not None else set()
    base = re.sub(r"[\[\]:*?/\\]", " ", str(name or "District")).strip() or "District"
    base = base[:31]
    candidate = base
    counter = 2
    while candidate in existing:
        suffix = f" {counter}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        counter += 1
    existing.add(candidate)
    return candidate


def ensure_dataframe(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    return pd.DataFrame()
