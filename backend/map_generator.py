from __future__ import annotations

import pandas as pd

from backend.utils import coerce_numeric, detect_column_map
from config import STATUS_COLORS


def _default_center() -> list[float]:
    return [5.1521, 46.1996]


def _expanded_bounds(bounds: list[list[float]]) -> list[list[float]]:
    south, west = bounds[0]
    north, east = bounds[1]
    if south == north:
        south -= 0.05
        north += 0.05
    if west == east:
        west -= 0.05
        east += 0.05
    return [[south, west], [north, east]]


def create_response_map(processed_df: pd.DataFrame, boundary_gdf=None, matches_df: pd.DataFrame | None = None):
    try:
        import folium
        from folium.plugins import Fullscreen, MarkerCluster, MeasureControl, MiniMap, MousePosition
    except ImportError as error:
        raise RuntimeError("Folium is required for the interactive map.") from error

    columns = detect_column_map(processed_df)
    lat_col = columns.get("latitude")
    lon_col = columns.get("longitude")
    district_col = columns.get("district")
    settlement_col = columns.get("settlement")

    center = _default_center()
    valid = pd.Series(False, index=processed_df.index)
    fit_lats: list[float] = []
    fit_lons: list[float] = []
    if lat_col and lon_col:
        lat = coerce_numeric(processed_df[lat_col])
        lon = coerce_numeric(processed_df[lon_col])
        valid = lat.between(-90, 90) & lon.between(-180, 180)
        if valid.any():
            center = [float(lat[valid].mean()), float(lon[valid].mean())]
            fit_lats.extend([float(lat[valid].min()), float(lat[valid].max())])
            fit_lons.extend([float(lon[valid].min()), float(lon[valid].max())])

    response_map = folium.Map(
        location=center,
        zoom_start=6,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
        width="100%",
        height="100%",
    )
    folium.TileLayer("CartoDB positron", name="Light basemap").add_to(response_map)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(response_map)
    folium.TileLayer("Esri.WorldImagery", name="Satellite imagery").add_to(response_map)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri and contributors",
        name="Topographic",
    ).add_to(response_map)
    Fullscreen(position="topleft", title="Expand to full screen", title_cancel="Exit full screen").add_to(response_map)
    MeasureControl(position="topleft", primary_length_unit="kilometers", primary_area_unit="sqkilometers").add_to(
        response_map
    )
    MousePosition(
        position="bottomright",
        separator=", ",
        prefix="Lat/Lon:",
        num_digits=5,
    ).add_to(response_map)
    MiniMap(toggle_display=True, position="bottomleft").add_to(response_map)

    if boundary_gdf is not None and len(boundary_gdf):
        try:
            boundary_layer = boundary_gdf.to_crs("EPSG:4326") if boundary_gdf.crs else boundary_gdf
            minx, miny, maxx, maxy = boundary_layer.total_bounds
            if all(pd.notna(value) for value in (minx, miny, maxx, maxy)):
                fit_lats.extend([float(miny), float(maxy)])
                fit_lons.extend([float(minx), float(maxx)])
            folium.GeoJson(
                boundary_layer,
                name="District boundaries",
                style_function=lambda _: {
                    "fillOpacity": 0.04,
                    "color": "#0078D4",
                    "weight": 1.8,
                },
                highlight_function=lambda _: {
                    "fillOpacity": 0.12,
                    "weight": 2.6,
                    "color": "#0B5DBB",
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
            f"Coordinates: {float(row[lat_col]):.5f}, {float(row[lon_col]):.5f}",
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

    legend_items = [
        ("Auto accepted", STATUS_COLORS.get("auto_accepted", "#107C10")),
        ("Needs review", STATUS_COLORS.get("needs_review", "#FFB900")),
        ("Unmatched", STATUS_COLORS.get("unresolved", "#C50F1F")),
        ("Already geocoded", STATUS_COLORS.get("already_geocoded", "#0078D4")),
    ]
    legend_rows = "".join(
        (
            f'<div><span style="background:{color}; border-radius:999px; display:inline-block; '
            f'height:9px; margin-right:7px; width:9px;"></span>{label}</div>'
        )
        for label, color in legend_items
    )
    response_map.get_root().html.add_child(
        folium.Element(
            f"""
            <div style="
                position: fixed;
                right: 18px;
                bottom: 34px;
                z-index: 9999;
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                box-shadow: 0 4px 14px rgba(15, 23, 42, 0.16);
                color: #0f172a;
                font-family: Arial, sans-serif;
                font-size: 12px;
                line-height: 1.35;
                padding: 10px 12px;
            ">
                <div style="font-weight: 700; margin-bottom: 6px;">Settlement status</div>
                <div style="display: grid; gap: 5px;">
                    {legend_rows}
                </div>
            </div>
            <style>
                .leaflet-control-layers-expanded {{
                    max-height: 320px;
                    overflow-y: auto;
                }}
            </style>
            """
        )
    )

    if fit_lats and fit_lons:
        response_map.fit_bounds(
            _expanded_bounds([[min(fit_lats), min(fit_lons)], [max(fit_lats), max(fit_lons)]]),
            padding=(28, 28),
        )

    folium.LayerControl(collapsed=False).add_to(response_map)
    return response_map
