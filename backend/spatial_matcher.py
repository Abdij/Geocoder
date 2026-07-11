from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Somalia's approximate bounding box, used only as a coarse sanity check for
# "is this coordinate nowhere near Somalia" / "are lat and lon swapped" -
# not a precise administrative boundary.
_SOMALIA_LAT_RANGE = (-1.7, 12.5)
_SOMALIA_LON_RANGE = (40.9, 51.5)

# (upper_bound_km, score) - first bound the distance falls under wins.
_DISTANCE_SCORE_BANDS = (
    (2.0, 100.0),
    (5.0, 90.0),
    (15.0, 70.0),
    (30.0, 40.0),
)
_DISTANCE_SCORE_BEYOND = 0.0


@dataclass
class SpatialEvidence:
    distance_km: float | None
    spatial_score: float | None
    submitted_in_own_district: bool | None
    submitted_in_candidate_district: bool | None
    candidate_in_own_district: bool | None
    possible_lat_lon_swap: bool
    outside_somalia: bool


def _in_range(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]


def is_outside_somalia(latitude: float | None, longitude: float | None) -> bool:
    """Coarse bounding-box check - flags coordinates nowhere near Somalia."""
    if latitude is None or longitude is None:
        return False
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    if pd.isna(lat) or pd.isna(lon):
        return False
    return not (_in_range(lat, _SOMALIA_LAT_RANGE) and _in_range(lon, _SOMALIA_LON_RANGE))


def detect_possible_lat_lon_swap(latitude: float | None, longitude: float | None) -> bool:
    """Flag coordinates that look like latitude/longitude were swapped.

    True when the coordinate as given falls outside Somalia (or is an
    impossible latitude), but swapping lat/lon would land inside Somalia.
    """
    if latitude is None or longitude is None:
        return False
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    if pd.isna(lat) or pd.isna(lon):
        return False

    as_given_valid = -90 <= lat <= 90 and -180 <= lon <= 180
    as_given_in_somalia = as_given_valid and _in_range(lat, _SOMALIA_LAT_RANGE) and _in_range(lon, _SOMALIA_LON_RANGE)
    if as_given_in_somalia:
        return False

    swapped_valid = -90 <= lon <= 90 and -180 <= lat <= 180
    if not swapped_valid:
        return False
    return _in_range(lon, _SOMALIA_LAT_RANGE) and _in_range(lat, _SOMALIA_LON_RANGE)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points.

    Uses geopy's geodesic distance when available (more accurate on the
    real ellipsoid), falling back to a haversine calculation so spatial
    scoring keeps working if geopy is not installed.
    """
    try:
        from geopy.distance import geodesic

        return float(geodesic((lat1, lon1), (lat2, lon2)).km)
    except ImportError:
        from math import asin, cos, radians, sin, sqrt

        earth_radius_km = 6371.0088
        d_lat = radians(lat2 - lat1)
        d_lon = radians(lon2 - lon1)
        a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
        return 2 * earth_radius_km * asin(sqrt(a))


def distance_score(distance_km: float | None) -> float | None:
    """Score a distance in km using the configured bands, or None if unavailable."""
    if distance_km is None:
        return None
    for upper_bound, score in _DISTANCE_SCORE_BANDS:
        if distance_km <= upper_bound:
            return score
    return _DISTANCE_SCORE_BEYOND


def point_in_named_boundary(
    latitude: float | None,
    longitude: float | None,
    boundary_gdf,
    name_column: str | None,
    admin_name: str | None,
) -> bool | None:
    """Whether a point falls inside the named boundary feature, or None if unavailable.

    Returns None (not False) when there's no boundary layer, no name column,
    no admin_name to match, or the point/feature can't be evaluated - callers
    should treat "unavailable" as no evidence either way, not as a conflict.
    """
    if boundary_gdf is None or not name_column or not admin_name:
        return None
    if latitude is None or longitude is None:
        return None
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if pd.isna(lat) or pd.isna(lon):
        return None

    from backend.text_normalizer import normalize_place_name

    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError:
        return None

    target = normalize_place_name(admin_name)
    if name_column not in boundary_gdf.columns:
        return None
    normalized_names = boundary_gdf[name_column].map(normalize_place_name)
    matches = boundary_gdf[normalized_names == target]
    if matches.empty:
        return None

    point = Point(float(lon), float(lat))
    try:
        return bool(matches.geometry.contains(point).any())
    except Exception:
        return None


def evaluate_spatial_evidence(
    submitted_latitude: float | None,
    submitted_longitude: float | None,
    candidate_latitude: float | None,
    candidate_longitude: float | None,
    submitted_district: str | None = None,
    candidate_district: str | None = None,
    boundary_gdf=None,
    boundary_district_column: str | None = None,
) -> SpatialEvidence:
    """Assemble the full set of spatial evidence for a candidate match.

    All fields degrade to None/False gracefully when coordinates or a
    boundary layer aren't available - missing evidence is never treated as
    a positive or negative signal by itself.
    """
    has_submitted_coords = submitted_latitude is not None and submitted_longitude is not None
    has_candidate_coords = candidate_latitude is not None and candidate_longitude is not None

    def _is_valid_point(lat, lon) -> bool:
        try:
            return -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
        except (TypeError, ValueError):
            return False

    # Distance requires two real-world points; an out-of-range submitted
    # coordinate (e.g. a data-entry error like latitude 99.1) is exactly the
    # kind of "invalid coordinate" this app already flags during validation -
    # feeding it to geopy anyway produces a nonsense distance and a confusing
    # warning, so treat it as unavailable rather than computing garbage.
    distance_km: float | None = None
    if (
        has_submitted_coords
        and has_candidate_coords
        and _is_valid_point(submitted_latitude, submitted_longitude)
        and _is_valid_point(candidate_latitude, candidate_longitude)
    ):
        try:
            distance_km = haversine_distance_km(
                float(submitted_latitude),
                float(submitted_longitude),
                lat2=float(candidate_latitude),
                lon2=float(candidate_longitude),
            )
        except (TypeError, ValueError):
            distance_km = None

    outside_somalia = is_outside_somalia(submitted_latitude, submitted_longitude) if has_submitted_coords else False
    possible_swap = detect_possible_lat_lon_swap(submitted_latitude, submitted_longitude) if has_submitted_coords else False

    submitted_in_own_district = None
    submitted_in_candidate_district = None
    candidate_in_own_district = None
    if has_submitted_coords:
        submitted_in_own_district = point_in_named_boundary(
            submitted_latitude, submitted_longitude, boundary_gdf, boundary_district_column, submitted_district
        )
        submitted_in_candidate_district = point_in_named_boundary(
            submitted_latitude, submitted_longitude, boundary_gdf, boundary_district_column, candidate_district
        )
    if has_candidate_coords:
        candidate_in_own_district = point_in_named_boundary(
            candidate_latitude, candidate_longitude, boundary_gdf, boundary_district_column, candidate_district
        )

    return SpatialEvidence(
        distance_km=round(distance_km, 3) if distance_km is not None else None,
        spatial_score=distance_score(distance_km),
        submitted_in_own_district=submitted_in_own_district,
        submitted_in_candidate_district=submitted_in_candidate_district,
        candidate_in_own_district=candidate_in_own_district,
        possible_lat_lon_swap=possible_swap,
        outside_somalia=outside_somalia,
    )
