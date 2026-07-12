from __future__ import annotations

import pandas as pd

from backend.confidence_scorer import ADMIN_CONTRADICTION_THRESHOLD
from backend.utils import coerce_numeric, detect_column_map
from config import MAX_AUTO_ACCEPT_DISTANCE_KM, STATUS_COLORS

# Leaflet core and the folium plugins used below (Fullscreen, MarkerCluster, MeasureControl,
# MiniMap, MousePosition) normally load their JS/CSS from public CDNs. Machines without internet
# access (the primary use case for the standalone desktop build) would render a blank map with no
# error, since the browser silently fails to fetch these scripts. Vendoring them under static/ and
# rewriting the CDN URLs below makes the map itself, markers, and controls work fully offline.
# Basemap imagery (OpenStreetMap/CartoDB/Esri tiles) still requires internet - that can't be
# bundled - but the map, points, and district boundaries no longer depend on it.
_LEAFLET_VENDOR_URL_MAP = {
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js": "app/static/leaflet_vendor/leaflet.js",
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css": "app/static/leaflet_vendor/leaflet.css",
    "https://code.jquery.com/jquery-3.7.1.min.js": "app/static/leaflet_vendor/jquery-3.7.1.min.js",
    "https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/js/bootstrap.bundle.min.js": "app/static/leaflet_vendor/bootstrap.bundle.min.js",
    "https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css": "app/static/leaflet_vendor/bootstrap.min.css",
    "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.2.0/css/all.min.css": "app/static/leaflet_vendor/all.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/Leaflet.awesome-markers/2.0.2/leaflet.awesome-markers.js": "app/static/leaflet_vendor/leaflet.awesome-markers.js",
    "https://cdnjs.cloudflare.com/ajax/libs/Leaflet.awesome-markers/2.0.2/leaflet.awesome-markers.css": "app/static/leaflet_vendor/leaflet.awesome-markers.css",
    "https://netdna.bootstrapcdn.com/bootstrap/3.0.0/css/bootstrap-glyphicons.css": "app/static/leaflet_vendor/bootstrap-glyphicons.css",
    "https://cdn.jsdelivr.net/npm/leaflet.fullscreen@3.0.0/Control.FullScreen.min.js": "app/static/leaflet_vendor/Control.FullScreen.min.js",
    "https://cdn.jsdelivr.net/npm/leaflet.fullscreen@3.0.0/Control.FullScreen.css": "app/static/leaflet_vendor/Control.FullScreen.css",
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.1.0/leaflet.markercluster.js": "app/static/leaflet_vendor/leaflet.markercluster.js",
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.1.0/MarkerCluster.css": "app/static/leaflet_vendor/MarkerCluster.css",
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.1.0/MarkerCluster.Default.css": "app/static/leaflet_vendor/MarkerCluster.Default.css",
    "https://cdn.jsdelivr.net/gh/ljagis/leaflet-measure@2.1.7/dist/leaflet-measure.min.js": "app/static/leaflet_vendor/leaflet-measure.min.js",
    "https://cdn.jsdelivr.net/gh/ljagis/leaflet-measure@2.1.7/dist/leaflet-measure.min.css": "app/static/leaflet_vendor/leaflet-measure.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet-minimap/3.6.1/Control.MiniMap.js": "app/static/leaflet_vendor/Control.MiniMap.js",
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet-minimap/3.6.1/Control.MiniMap.css": "app/static/leaflet_vendor/Control.MiniMap.css",
    "https://cdn.jsdelivr.net/gh/ardhi/Leaflet.MousePosition/src/L.Control.MousePosition.min.js": "app/static/leaflet_vendor/L.Control.MousePosition.min.js",
    "https://cdn.jsdelivr.net/gh/ardhi/Leaflet.MousePosition/src/L.Control.MousePosition.min.css": "app/static/leaflet_vendor/L.Control.MousePosition.min.css",
    "https://cdn.jsdelivr.net/gh/python-visualization/folium/folium/templates/leaflet.awesome.rotate.min.css": "app/static/leaflet_vendor/leaflet.awesome.rotate.min.css",
}


def _patch_branca_links_for_offline_use() -> None:
    """Rewrite CDN URLs to local vendored copies the instant a Link is constructed.

    Folium/branca plugins (Fullscreen, MarkerCluster, MeasureControl, MiniMap, MousePosition,
    the base Leaflet/jQuery/Bootstrap includes) register their JavascriptLink/CssLink children
    lazily inside each element's render() method - which folium-streamlit and _repr_html_() both
    call themselves, outside our control and possibly more than once. Patching the URL at
    construction time (rather than walking the tree after the fact) works regardless of when or
    how many times rendering happens.
    """
    import branca.element as branca_element

    if getattr(branca_element.Link, "_ocha_offline_patched", False):
        return

    original_init = branca_element.Link.__init__

    def patched_init(self, url, *args, **kwargs):
        original_init(self, _LEAFLET_VENDOR_URL_MAP.get(url, url), *args, **kwargs)

    branca_element.Link.__init__ = patched_init
    branca_element.Link._ocha_offline_patched = True


_patch_branca_links_for_offline_use()


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
        submitted_layer = folium.FeatureGroup(name="Submitted coordinates + distance", show=False)
        for _, match in matches_df.iterrows():
            lat = pd.to_numeric(pd.Series([match.get("latitude")]), errors="coerce").iloc[0]
            lon = pd.to_numeric(pd.Series([match.get("longitude")]), errors="coerce").iloc[0]
            if pd.isna(lat) or pd.isna(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            status = str(match.get("status", "needs_review")).lower()
            if status not in {"needs_review", "unresolved", "rejected"}:
                continue

            district_score = pd.to_numeric(pd.Series([match.get("district_score")]), errors="coerce").iloc[0]
            region_score = pd.to_numeric(pd.Series([match.get("region_score")]), errors="coerce").iloc[0]
            distance_km = pd.to_numeric(pd.Series([match.get("distance_km")]), errors="coerce").iloc[0]
            admin_conflict = (pd.notna(district_score) and district_score < ADMIN_CONTRADICTION_THRESHOLD) or (
                pd.notna(region_score) and region_score < ADMIN_CONTRADICTION_THRESHOLD
            )
            spatial_conflict = pd.notna(distance_km) and distance_km > MAX_AUTO_ACCEPT_DISTANCE_KM

            color = STATUS_COLORS.get(status, "#FFB900")
            conflict_labels = []
            if admin_conflict:
                conflict_labels.append("Administrative conflict")
            if spatial_conflict:
                conflict_labels.append("Spatial conflict")
            # A dashed, thicker ring distinguishes a flagged conflict from a
            # plain low-confidence match at a glance, without needing a
            # whole separate color scale.
            marker_weight = 5 if conflict_labels else 3
            dash_array = "4,3" if conflict_labels else None

            popup_lines = [
                f"<b>{match.get('submitted_settlement', 'Submitted settlement')}</b>",
                f"Suggested: {match.get('suggested_settlement', '')}",
                f"District: {match.get('suggested_district', '')}",
                f"Confidence: {match.get('confidence', '')}",
                f"Status: {status.replace('_', ' ').title()}",
            ]
            if conflict_labels:
                popup_lines.append(f"⚠ {', '.join(conflict_labels)}")
            if pd.notna(distance_km):
                popup_lines.append(f"Distance from submitted point: {distance_km:.1f} km")

            record_id = match.get("record_id")
            folium.CircleMarker(
                location=[float(lat), float(lon)],
                radius=8,
                color=color,
                weight=marker_weight,
                dash_array=dash_array,
                fill=True,
                fill_color="#ffffff",
                fill_opacity=0.65,
                popup=folium.Popup("<br>".join(popup_lines), max_width=320),
                # Encodes the record so the dashboard can read back which marker
                # was clicked (via st_folium's last_object_clicked_tooltip) and
                # open that record for review without leaving the map.
                tooltip=f"map-select:{int(record_id)}" if pd.notna(record_id) else None,
            ).add_to(review_layer)

            # The submitted coordinate is only meaningful for records that
            # had an invalid (not merely missing) GPS value - draw it plus a
            # line to the suggested candidate so a reviewer can see how far
            # off the original point was.
            submitted_lat = pd.to_numeric(pd.Series([match.get("submitted_latitude")]), errors="coerce").iloc[0]
            submitted_lon = pd.to_numeric(pd.Series([match.get("submitted_longitude")]), errors="coerce").iloc[0]
            if pd.notna(submitted_lat) and pd.notna(submitted_lon):
                folium.CircleMarker(
                    location=[float(submitted_lat), float(submitted_lon)],
                    radius=5,
                    color="#605E5C",
                    fill=True,
                    fill_color="#605E5C",
                    fill_opacity=0.85,
                    popup=folium.Popup(
                        f"Submitted coordinate for {match.get('submitted_settlement', '')}"
                        f"<br>({float(submitted_lat):.5f}, {float(submitted_lon):.5f})",
                        max_width=260,
                    ),
                ).add_to(submitted_layer)
                line_tooltip = (
                    f"{distance_km:.1f} km to suggested candidate" if pd.notna(distance_km) else "Distance unavailable"
                )
                folium.PolyLine(
                    locations=[[float(submitted_lat), float(submitted_lon)], [float(lat), float(lon)]],
                    color="#605E5C",
                    weight=2,
                    dash_array="6,6",
                    tooltip=line_tooltip,
                ).add_to(submitted_layer)

        review_layer.add_to(response_map)
        submitted_layer.add_to(response_map)

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
