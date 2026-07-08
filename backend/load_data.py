from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from config import (
    SAMPLE_BOUNDARIES,
    SAMPLE_GAZETTEER,
    SAMPLE_RESPONSE,
    SUPPORTED_SPATIAL_EXTENSIONS,
    SUPPORTED_TABLE_EXTENSIONS,
    UPLOADS_DIR,
)


class DataLoadError(RuntimeError):
    """Raised when a user-supplied data file cannot be read cleanly."""


def _name_and_suffix(file_or_path: Any) -> tuple[str, str]:
    if isinstance(file_or_path, (str, Path)):
        path = Path(file_or_path)
        return path.name, path.suffix.lower()
    name = getattr(file_or_path, "name", "uploaded_file")
    return name, Path(name).suffix.lower()


def assign_source_row_ids(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "_source_row_id" not in df.columns:
        df.insert(0, "_source_row_id", range(2, len(df) + 2))
    return df


def save_uploaded_file(uploaded_file: Any, target_dir: Path = UPLOADS_DIR) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    name, suffix = _name_and_suffix(uploaded_file)
    safe_name = Path(name).name or f"upload{suffix}"
    target = target_dir / safe_name
    if target.exists():
        stem = target.stem
        counter = 2
        while target.exists():
            target = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    uploaded_file.seek(0)
    with target.open("wb") as destination:
        destination.write(uploaded_file.read())
    uploaded_file.seek(0)
    return target


def read_tabular_file(file_or_path: Any, add_row_ids: bool = True) -> pd.DataFrame:
    name, suffix = _name_and_suffix(file_or_path)
    if suffix not in SUPPORTED_TABLE_EXTENSIONS:
        raise DataLoadError(
            f"{name} is not a supported table format. Use CSV, XLSX, or XLS."
        )

    try:
        if hasattr(file_or_path, "seek"):
            file_or_path.seek(0)
        if suffix == ".csv":
            df = pd.read_csv(file_or_path)
        else:
            df = pd.read_excel(file_or_path, sheet_name=0)
    except Exception as error:
        raise DataLoadError(f"Could not read {name}. Check that the file is not corrupt.") from error

    if df.empty:
        raise DataLoadError(f"{name} loaded successfully, but it contains no records.")

    return assign_source_row_ids(df) if add_row_ids else df


def _copy_upload_to_temp(uploaded_file: Any, temp_dir: Path) -> Path:
    name, suffix = _name_and_suffix(uploaded_file)
    target = temp_dir / Path(name).name
    uploaded_file.seek(0)
    with target.open("wb") as destination:
        shutil.copyfileobj(uploaded_file, destination)
    uploaded_file.seek(0)
    return target


def read_spatial_file(file_or_path: Any):
    name, suffix = _name_and_suffix(file_or_path)
    if suffix not in SUPPORTED_SPATIAL_EXTENSIONS:
        raise DataLoadError(
            f"{name} is not a supported spatial format. Use GeoJSON, GeoPackage, Shapefile, or ZIP."
        )

    try:
        import geopandas as gpd
    except ImportError as error:
        raise DataLoadError("GeoPandas is required to read spatial boundary layers.") from error

    try:
        if isinstance(file_or_path, (str, Path)):
            path = Path(file_or_path)
            if suffix == ".zip":
                with tempfile.TemporaryDirectory() as temp:
                    temp_dir = Path(temp)
                    with zipfile.ZipFile(path) as archive:
                        archive.extractall(temp_dir)
                    shp_files = list(temp_dir.rglob("*.shp"))
                    if not shp_files:
                        raise DataLoadError("The ZIP file does not contain a Shapefile.")
                    return gpd.read_file(shp_files[0])
            return gpd.read_file(path)

        with tempfile.TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            path = _copy_upload_to_temp(file_or_path, temp_dir)
            if suffix == ".zip":
                with zipfile.ZipFile(path) as archive:
                    archive.extractall(temp_dir)
                shp_files = list(temp_dir.rglob("*.shp"))
                if not shp_files:
                    raise DataLoadError("The ZIP file does not contain a Shapefile.")
                return gpd.read_file(shp_files[0])
            return gpd.read_file(path)
    except DataLoadError:
        raise
    except Exception as error:
        raise DataLoadError(f"Could not read {name} as a spatial layer.") from error


def load_sample_datasets() -> tuple[pd.DataFrame, pd.DataFrame, Any | None]:
    response_df = read_tabular_file(SAMPLE_RESPONSE)
    gazetteer_df = read_tabular_file(SAMPLE_GAZETTEER, add_row_ids=False)
    boundary_gdf = None
    if SAMPLE_BOUNDARIES.exists():
        try:
            boundary_gdf = read_spatial_file(SAMPLE_BOUNDARIES)
        except DataLoadError:
            boundary_gdf = None
    return response_df, gazetteer_df, boundary_gdf
