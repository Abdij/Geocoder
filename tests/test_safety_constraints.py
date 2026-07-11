from __future__ import annotations

from backend.confidence_scorer import determine_match_status


def test_high_confidence_with_no_issues_is_auto_accepted():
    result = determine_match_status(confidence=97.0, district_score=100.0, region_score=100.0)
    assert result.status == "auto_accepted"
    assert result.blocked_reasons == []


def test_moderate_confidence_is_needs_review():
    result = determine_match_status(confidence=90.0, district_score=100.0, region_score=100.0)
    assert result.status == "needs_review"


def test_low_confidence_is_unresolved():
    result = determine_match_status(confidence=50.0)
    assert result.status == "unresolved"


def test_district_contradiction_blocks_auto_accept_even_at_high_confidence():
    result = determine_match_status(confidence=99.0, district_score=10.0, region_score=100.0)
    assert result.status != "auto_accepted"
    assert "district_contradiction" in result.blocked_reasons


def test_region_contradiction_blocks_auto_accept():
    result = determine_match_status(confidence=99.0, district_score=100.0, region_score=10.0)
    assert result.status != "auto_accepted"
    assert "region_contradiction" in result.blocked_reasons


def test_unknown_district_does_not_trigger_contradiction():
    # _admin_score() returns 60 for "unknown", not a contradiction - the
    # neutral-missing value must stay above ADMIN_CONTRADICTION_THRESHOLD.
    result = determine_match_status(confidence=97.0, district_score=60.0, region_score=60.0)
    assert result.status == "auto_accepted"
    assert result.blocked_reasons == []


def test_ambiguous_national_name_blocks_auto_accept():
    result = determine_match_status(confidence=99.0, is_ambiguous_national_name=True)
    assert result.status != "auto_accepted"
    assert "ambiguous_national_name" in result.blocked_reasons


def test_excessive_spatial_distance_blocks_auto_accept():
    result = determine_match_status(confidence=99.0, spatial_distance_km=50.0)
    assert result.status != "auto_accepted"
    assert "spatial_distance_exceeded" in result.blocked_reasons


def test_spatial_distance_within_max_does_not_block():
    result = determine_match_status(confidence=97.0, spatial_distance_km=10.0)
    assert result.status == "auto_accepted"


def test_near_tied_top_candidates_blocks_auto_accept():
    result = determine_match_status(confidence=96.0, second_candidate_confidence=93.0)
    assert result.status != "auto_accepted"
    assert "ambiguous_top_candidates" in result.blocked_reasons


def test_clearly_separated_top_candidates_does_not_block():
    result = determine_match_status(confidence=97.0, second_candidate_confidence=60.0)
    assert result.status == "auto_accepted"


def test_repeated_rejection_blocks_auto_accept():
    result = determine_match_status(confidence=99.0, rejection_count=2)
    assert result.status != "auto_accepted"
    assert "repeated_rejection" in result.blocked_reasons


def test_single_rejection_does_not_block():
    result = determine_match_status(confidence=97.0, rejection_count=1)
    assert result.status == "auto_accepted"


def test_missing_admin_info_blocks_auto_accept():
    result = determine_match_status(confidence=99.0, candidate_missing_admin_info=True)
    assert result.status != "auto_accepted"
    assert "candidate_missing_admin_info" in result.blocked_reasons


def test_blocked_record_still_gets_needs_review_if_confidence_qualifies():
    result = determine_match_status(confidence=90.0, is_ambiguous_national_name=True)
    assert result.status == "needs_review"


def test_blocked_record_drops_to_unresolved_if_confidence_too_low():
    result = determine_match_status(confidence=50.0, is_ambiguous_national_name=True)
    assert result.status == "unresolved"


def test_multiple_blocking_reasons_are_all_reported():
    result = determine_match_status(
        confidence=99.0,
        district_score=10.0,
        spatial_distance_km=50.0,
        rejection_count=3,
    )
    assert {"district_contradiction", "spatial_distance_exceeded", "repeated_rejection"} <= set(result.blocked_reasons)
