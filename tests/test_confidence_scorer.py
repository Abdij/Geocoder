from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.confidence_scorer import (
    composite_confidence,
    historical_evidence_score,
    rejection_penalty,
)


def test_historical_score_none_with_no_approvals():
    assert historical_evidence_score(0) is None


def test_historical_score_weak_for_single_approval():
    assert historical_evidence_score(1) == 40.0


def test_historical_score_moderate_for_two_to_four_approvals():
    assert historical_evidence_score(2) == 70.0
    assert historical_evidence_score(4) == 70.0


def test_historical_score_strong_for_five_or_more_approvals():
    assert historical_evidence_score(5) == 100.0
    assert historical_evidence_score(20) == 100.0


def test_historical_score_decays_for_stale_approvals():
    now = datetime.now(timezone.utc)
    stale_date = (now - timedelta(days=800)).isoformat()
    fresh_date = (now - timedelta(days=10)).isoformat()
    stale_score = historical_evidence_score(5, last_approved_at=stale_date, reference_time=now)
    fresh_score = historical_evidence_score(5, last_approved_at=fresh_date, reference_time=now)
    assert stale_score < fresh_score
    assert fresh_score == 100.0


def test_rejection_penalty_zero_when_never_rejected():
    assert rejection_penalty(0) == 0.0


def test_rejection_penalty_scales_and_caps():
    assert rejection_penalty(1) == 15.0
    assert rejection_penalty(2) == 30.0
    assert rejection_penalty(10) == 30.0  # capped


def test_composite_confidence_all_components_available():
    result = composite_confidence(
        name_score=100.0,
        district_score=100.0,
        region_score=100.0,
        spatial_score=100.0,
        historical_score=100.0,
        semantic_score=100.0,
    )
    assert result.overall_confidence == 100.0


def test_composite_confidence_redistributes_missing_weight():
    # Only name+district available; their relative 35:20 weighting should
    # still produce 100 when both underlying scores are 100, since the
    # missing components' weight is redistributed rather than counted as 0.
    result = composite_confidence(
        name_score=100.0,
        district_score=100.0,
        region_score=None,
        spatial_score=None,
        historical_score=None,
        semantic_score=None,
    )
    assert result.overall_confidence == 100.0


def test_composite_confidence_missing_evidence_is_not_penalized():
    with_all = composite_confidence(80.0, 80.0, 80.0, 80.0, 80.0, 80.0)
    with_missing = composite_confidence(80.0, 80.0, 80.0, None, None, None)
    assert round(with_all.overall_confidence) == round(with_missing.overall_confidence)


def test_composite_confidence_applies_rejection_penalty():
    without_penalty = composite_confidence(90.0, 90.0, 90.0, rejection_penalty_value=0.0)
    with_penalty = composite_confidence(90.0, 90.0, 90.0, rejection_penalty_value=30.0)
    assert with_penalty.overall_confidence == without_penalty.overall_confidence - 30.0


def test_composite_confidence_never_goes_below_zero_from_penalty():
    result = composite_confidence(10.0, 10.0, 10.0, rejection_penalty_value=30.0)
    assert result.overall_confidence == 0.0


def test_composite_confidence_zero_when_nothing_available():
    result = composite_confidence(None, None, None)
    assert result.overall_confidence == 0.0
    assert "no scoring evidence" in result.explanation.lower()


def test_composite_confidence_explanation_mentions_missing_components():
    result = composite_confidence(90.0, 90.0, 90.0, spatial_score=None, historical_score=None, semantic_score=None)
    assert "spatial" in result.explanation
    assert "historical" in result.explanation
    assert "semantic" in result.explanation
