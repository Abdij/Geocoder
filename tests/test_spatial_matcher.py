from __future__ import annotations

from backend.spatial_matcher import (
    detect_possible_lat_lon_swap,
    distance_score,
    evaluate_spatial_evidence,
    haversine_distance_km,
    is_outside_somalia,
)


def test_haversine_distance_is_zero_for_identical_points():
    assert haversine_distance_km(3.1167, 43.65, 3.1167, 43.65) == 0.0


def test_haversine_distance_known_pair_is_reasonable():
    # Baidoa to Mogadishu is roughly 240km as the crow flies.
    distance = haversine_distance_km(3.1167, 43.65, 2.0469, 45.3182)
    assert 200 < distance < 280


def test_distance_score_bands():
    assert distance_score(0) == 100.0
    assert distance_score(1.9) == 100.0
    assert distance_score(2.0) == 100.0
    assert distance_score(4.9) == 90.0
    assert distance_score(14.9) == 70.0
    assert distance_score(29.9) == 40.0
    assert distance_score(30.0) == 40.0
    assert distance_score(30.1) == 0.0
    assert distance_score(100) == 0.0


def test_distance_score_is_none_when_distance_unavailable():
    assert distance_score(None) is None


def test_is_outside_somalia_true_for_far_away_point():
    assert is_outside_somalia(40.7128, -74.0060) is True  # New York


def test_is_outside_somalia_false_for_somali_point():
    assert is_outside_somalia(2.0469, 45.3182) is False  # Mogadishu


def test_is_outside_somalia_false_when_coordinates_missing():
    assert is_outside_somalia(None, None) is False


def test_detect_lat_lon_swap_true_when_swapped_coordinate_is_in_somalia():
    # Mogadishu is (2.0469, 45.3182); swapped would be (45.3182, 2.0469).
    assert detect_possible_lat_lon_swap(45.3182, 2.0469) is True


def test_detect_lat_lon_swap_false_for_normal_somali_coordinate():
    assert detect_possible_lat_lon_swap(2.0469, 45.3182) is False


def test_detect_lat_lon_swap_false_when_neither_orientation_is_in_somalia():
    assert detect_possible_lat_lon_swap(40.7128, -74.0060) is False


def test_evaluate_spatial_evidence_with_full_coordinates():
    evidence = evaluate_spatial_evidence(
        submitted_latitude=3.1167,
        submitted_longitude=43.65,
        candidate_latitude=3.1167,
        candidate_longitude=43.65,
    )
    assert evidence.distance_km == 0.0
    assert evidence.spatial_score == 100.0
    assert evidence.outside_somalia is False
    assert evidence.possible_lat_lon_swap is False


def test_evaluate_spatial_evidence_missing_submitted_coords_is_unavailable_not_zero():
    evidence = evaluate_spatial_evidence(
        submitted_latitude=None,
        submitted_longitude=None,
        candidate_latitude=3.1167,
        candidate_longitude=43.65,
    )
    assert evidence.distance_km is None
    assert evidence.spatial_score is None
    assert evidence.outside_somalia is False


def test_evaluate_spatial_evidence_boundary_checks_are_none_without_boundary_layer():
    evidence = evaluate_spatial_evidence(
        submitted_latitude=3.1167,
        submitted_longitude=43.65,
        candidate_latitude=3.1167,
        candidate_longitude=43.65,
        submitted_district="Baidoa",
        candidate_district="Baidoa",
        boundary_gdf=None,
        boundary_district_column=None,
    )
    assert evidence.submitted_in_own_district is None
    assert evidence.submitted_in_candidate_district is None
    assert evidence.candidate_in_own_district is None


def test_evaluate_spatial_evidence_out_of_range_submitted_latitude_skips_distance(recwarn):
    # A real-world data-entry error (e.g. latitude 99.1) must not be fed to
    # the distance calculation - it should be treated as unavailable, not
    # produce a nonsense distance or a geopy warning.
    evidence = evaluate_spatial_evidence(
        submitted_latitude=99.1,
        submitted_longitude=44.77,
        candidate_latitude=2.3076,
        candidate_longitude=44.7723,
    )
    assert evidence.distance_km is None
    assert evidence.spatial_score is None
    assert len(recwarn) == 0


def test_evaluate_spatial_evidence_out_of_range_candidate_coordinate_skips_distance():
    evidence = evaluate_spatial_evidence(
        submitted_latitude=2.3076,
        submitted_longitude=44.7723,
        candidate_latitude=199.0,
        candidate_longitude=44.7723,
    )
    assert evidence.distance_km is None
    assert evidence.spatial_score is None
