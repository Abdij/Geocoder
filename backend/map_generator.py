from __future__ import annotations

import pandas as pd

from backend.utils import coerce_numeric, detect_column_map
from config import STATUS_COLORS


def _default_center() -> list[float]:
    return [5.1521, 46.1996]


def create_response_map(processed_df: pd.DataFrame, boundary_gdf=None, matches_df: pd.DataFrame | None = None):
    try:
        import folium
        from folium.plugins import MarkerCluster
    except ImportError as error:
        raise RuntimeError("Folium is required for the interactive map.") from error

    columns = detect_column_map(processed_df)
    lat_col = columns.get("latitude")
    lon_col = columns.get("longitude")
    district_col = columns.get("district")
    settlement_col = columns.get("settlement")

    center = _default_center()
    valid = pd.Series(False, index=processed_df.index)
    if lat_col and lon_col:
        lat = coerce_numeric(processed_df[lat_col])
        lon = coerce_numeric(processed_df[lon_col])
        valid = lat.between(-90, 90) & lon.between(-180, 180)
        if valid.any():
            center = [float(lat[valid].mean()), float(lon[valid].mean())]

    response_map = folium.Map(location=center, zoom_start=6, tiles="CartoDB positron", control_scale=True)

    if boundary_gdf is not None and len(boundary_gdf):
        try:
            boundary_layer = boundary_gdf.to_crs("EPSG:4326") if boundary_gdf.crs else boundary_gdf
            folium.GeoJson(
                boundary_layer,
                name="District boundaries",
                style_function=lambda _: {
                    "fillOpacity": 0.03,
                    "color": "#0078D4",
                    "weight": 1.2,
                },
            ).add_to(response_map)
        except Exception:
            pass

    cluster = MarkerCluster(name="Settlement response records").add_to(response_map)
    rows = processed_df.loc[valid].copy()
    for _, row in rows.iterrows():
        status = str(row.get("Match Status", "already_geocoded")).lower()
        color = STATUS_COLORS.get(status, "#0078D4")
        popup_lines = [
            f"<b>{row.get(settlement_col, 'Settlement')}</b>" if settlement_col else "<b>Settlement</b>",
            f"District: {row.get(district_col, 'Not specified')}" if district_col else "District: Not specified",
            f"Status: {status.replace('_', ' ').title()}",
        ]
        if "Match Confidence" in row and pd.notna(row["Match Confidence"]):
            popup_lines.append(f"Confidence: {row['Match Confidence']}")
        folium.CircleMarker(
            location=[float(row[lat_col]), float(row[lon_col])],
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.78,
            popup=folium.Popup("<br>".join(popup_lines), max_width=300),
        ).add_to(cluster)

    if matches_df is not None and not matches_df.empty:
        review_layer = folium.FeatureGroup(name="Review candidates", show=True)
        for _, match in matches_df.iterrows():
            lat = pd.to_numeric(pd.Series([match.get("latitude")]), errors="coerce").iloc[0]
            lon = pd.to_numeric(pd.Series([match.get("longitude")]), errors="coerce").iloc[0]
            if pd.isna(lat) or pd.isna(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            status = str(match.get("status", "needs_review")).lower()
            if status not in {"needs_review", "unresolved", "rejected"}:
                continue
            color = STATUS_COLORS.get(status, "#FFB900")
            popup = (
                f"<b>{match.get('submitted_settlement', 'Submitted settlement')}</b><br>"
                f"Suggested: {match.get('suggested_settlement', '')}<br>"
                f"District: {match.get('suggested_district', '')}<br>"
                f"Confidence: {match.get('confidence', '')}<br>"
                f"Status: {status.replace('_', ' ').title()}"
            )
            folium.CircleMarker(
                location=[float(lat), float(lon)],
                radius=8,
                color=color,
                weight=3,
                fill=True,
                fill_color="#ffffff",
                fill_opacity=0.65,
                popup=folium.Popup(popup, max_width=320),
            ).add_to(review_layer)
        review_layer.add_to(response_map)

    folium.LayerControl(collapsed=False).add_to(response_map)
    return response_map
