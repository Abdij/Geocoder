from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd

from config import DEFAULT_CRS
from backend.geocoder import create_geodataframe
from backend.utils import output_path, safe_slug


GIS_OUTPUT_KEYS = {"GeoPackage", "GeoJSON", "Shapefile ZIP"}


def _selected_keys(output_keys: Iterable[str] | None) -> set[str]:
    return set(output_keys) if output_keys is not None else set(GIS_OUTPUT_KEYS)


def _zip_directory(directory: Path, zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(directory))
    return zip_path


def _prepare_shapefile_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    used: set[str] = set()
    for column in df.columns:
        if column == "geometry":
            continue
        candidate = safe_slug(column, "field")[:10].upper()
        base = candidate or "FIELD"
        counter = 2
        while candidate in used:
            suffix = str(counter)
            candidate = f"{base[:10 - len(suffix)]}{suffix}"
            counter += 1
        used.add(candidate)
        rename_map[column] = candidate
    return df.rename(columns=rename_map)


def export_gis_outputs(
    processed_df: pd.DataFrame,
    crs: str = DEFAULT_CRS,
    output_keys: Iterable[str] | None = None,
) -> dict[str, str]:
    results: dict[str, str] = {}
    selected = _selected_keys(output_keys)
    if not selected:
        return results

    gdf = create_geodataframe(processed_df, crs=crs)
    if gdf.empty:
        raise ValueError("No records with valid coordinates are available for GIS export.")

    if "GeoPackage" in selected:
        gpkg_path = output_path("ocha_settlement_response.gpkg")
        gdf.to_file(gpkg_path, layer="settlement_response", driver="GPKG")
        results["GeoPackage"] = str(gpkg_path)

    if "GeoJSON" in selected:
        geojson_path = output_path("ocha_settlement_response.geojson")
        gdf.to_file(geojson_path, driver="GeoJSON")
        results["GeoJSON"] = str(geojson_path)

    if "Shapefile ZIP" in selected:
        shapefile_dir = output_path("ocha_settlement_response_shapefile").with_suffix("")
        if shapefile_dir.exists():
            shutil.rmtree(shapefile_dir)
        shapefile_dir.mkdir(parents=True, exist_ok=True)
        shapefile_gdf = _prepare_shapefile_columns(gdf.copy())
        shapefile_path = shapefile_dir / "settlement_response.shp"
        shapefile_gdf.to_file(shapefile_path, driver="ESRI Shapefile")
        zip_path = output_path("ocha_settlement_response_shapefile.zip")
        _zip_directory(shapefile_dir, zip_path)
        results["Shapefile ZIP"] = str(zip_path)

    return results
