from __future__ import annotations

import pandas as pd

from backend.map_generator import create_response_map


def _processed_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Settlement": ["Baidoa", "Kaharey"],
            "District": ["Baidoa", "Doolow"],
            "Latitude": [3.1167, 4.14],
            "Longitude": [43.65, 42.19],
            "Match Status": ["already_geocoded", "needs_review"],
            "Match Confidence": [None, 71.4],
        }
    )


def _matches_df_with_conflicts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "submitted_settlement": "Kaharey Health Center",
                "submitted_district": "Doolow",
                "suggested_settlement": "Kaharey",
                "suggested_district": "Luuq",
                "latitude": 4.14,
                "longitude": 42.19,
                "confidence": 71.4,
                "status": "needs_review",
                "district_score": 20.0,
                "region_score": 100.0,
                "distance_km": 45.0,
                "submitted_latitude": 4.30,
                "submitted_longitude": 42.00,
            }
        ]
    )


def test_create_response_map_works_without_boundary_layer():
    m = create_response_map(_processed_df(), None, None)
    assert m is not None


def test_create_response_map_works_with_empty_matches():
    m = create_response_map(_processed_df(), None, pd.DataFrame())
    assert m is not None


def test_map_draws_line_and_submitted_marker_for_flagged_conflict():
    m = create_response_map(_processed_df(), None, _matches_df_with_conflicts())
    html = m._repr_html_()
    assert "polyline" in html.lower()
    assert "Submitted coordinate for" in html


def test_map_popup_mentions_conflicts_when_flagged():
    m = create_response_map(_processed_df(), None, _matches_df_with_conflicts())
    html = m._repr_html_()
    assert "Administrative conflict" in html
    assert "Spatial conflict" in html


def test_map_omits_submitted_marker_when_submitted_coordinate_missing():
    matches_df = _matches_df_with_conflicts()
    matches_df["submitted_latitude"] = None
    matches_df["submitted_longitude"] = None
    m = create_response_map(_processed_df(), None, matches_df)
    html = m._repr_html_()
    assert "Submitted coordinate for" not in html
