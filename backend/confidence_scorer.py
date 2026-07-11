from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Name similarity carries the most weight since a submitted settlement name is
# the primary signal analysts are trying to resolve; the rest corroborate it.
DEFAULT_WEIGHTS: dict[str, float] = {
    "name": 0.35,
    "district": 0.20,
    "region": 0.10,
    "spatial": 0.15,
    "historical": 0.10,
    "semantic": 0.10,
}

_STRONG_APPROVAL_THRESHOLD = 5
_MODERATE_APPROVAL_THRESHOLD = 2
_STRONG_SCORE = 100.0
_MODERATE_SCORE = 70.0
_WEAK_SCORE = 40.0
_STALE_APPROVAL_DAYS = 730  # ~2 years
_STALE_DECAY_POINTS = 15.0

_REJECTION_PENALTY_PER_COUNT = 15.0
_REJECTION_PENALTY_CAP = 30.0


def historical_evidence_score(
    approval_count: int,
    last_approved_at: str | None = None,
    reference_time: datetime | None = None,
) -> float | None:
    """Score how much prior analyst approval history supports a candidate.

    Transparent tiering rather than a trained model: 5+ approvals is strong
    evidence, 2-4 is moderate, 1 is weak, and 0 means no evidence is
    available at all (None, not a low score - the app should not treat
    "never reviewed before" as a mark against a candidate).

    A stale-approval decay applies when the most recent approval is old
    (roughly 2+ years), since naming conventions and gazetteer coverage can
    drift over that time; this is a fixed, documented adjustment, not a
    learned one.
    """
    if approval_count <= 0:
        return None
    if approval_count >= _STRONG_APPROVAL_THRESHOLD:
        score = _STRONG_SCORE
    elif approval_count >= _MODERATE_APPROVAL_THRESHOLD:
        score = _MODERATE_SCORE
    else:
        score = _WEAK_SCORE

    if last_approved_at:
        try:
            approved_dt = datetime.fromisoformat(last_approved_at)
            if approved_dt.tzinfo is None:
                approved_dt = approved_dt.replace(tzinfo=timezone.utc)
            now = reference_time or datetime.now(timezone.utc)
            age_days = (now - approved_dt).total_seconds() / 86400
            if age_days > _STALE_APPROVAL_DAYS:
                score = max(_WEAK_SCORE, score - _STALE_DECAY_POINTS)
        except (TypeError, ValueError):
            pass

    return score


def rejection_penalty(rejection_count: int) -> float:
    """A fixed, documented confidence penalty for repeatedly rejected candidates.

    15 points per prior rejection of this exact (submitted context ->
    candidate) pair, capped at 30 points, so one stray rejection doesn't
    permanently blacklist a candidate but a consistent pattern does.
    """
    if rejection_count <= 0:
        return 0.0
    return min(_REJECTION_PENALTY_CAP, rejection_count * _REJECTION_PENALTY_PER_COUNT)


@dataclass
class ConfidenceResult:
    overall_confidence: float
    name_score: float | None
    district_score: float | None
    region_score: float | None
    spatial_score: float | None
    historical_score: float | None
    semantic_score: float | None
    rejection_penalty: float
    explanation: str


def composite_confidence(
    name_score: float | None,
    district_score: float | None,
    region_score: float | None,
    spatial_score: float | None = None,
    historical_score: float | None = None,
    semantic_score: float | None = None,
    rejection_penalty_value: float = 0.0,
    weights: dict[str, float] | None = None,
) -> ConfidenceResult:
    """Combine every available evidence component into one transparent score.

    Weight for any missing (None) component is redistributed proportionally
    across the components that ARE available, rather than treating missing
    evidence as either a positive or a negative signal. If nothing at all is
    available, confidence is 0 (unresolved, not accepted by default).
    """
    weights = weights or DEFAULT_WEIGHTS
    components = {
        "name": name_score,
        "district": district_score,
        "region": region_score,
        "spatial": spatial_score,
        "historical": historical_score,
        "semantic": semantic_score,
    }
    available = {key: value for key, value in components.items() if value is not None}

    if not available:
        return ConfidenceResult(
            overall_confidence=0.0,
            name_score=name_score,
            district_score=district_score,
            region_score=region_score,
            spatial_score=spatial_score,
            historical_score=historical_score,
            semantic_score=semantic_score,
            rejection_penalty=rejection_penalty_value,
            explanation="No scoring evidence was available for this record; confidence defaults to 0.",
        )

    available_weight_total = sum(weights[key] for key in available)
    redistributed = {key: weights[key] / available_weight_total for key in available}
    overall = sum(available[key] * redistributed[key] for key in available)
    overall = max(0.0, overall - rejection_penalty_value)

    parts = ", ".join(
        f"{key} {available[key]:.1f}% (weight {redistributed[key] * 100:.0f}%)" for key in available
    )
    explanation = f"Weighted from: {parts}."
    if rejection_penalty_value:
        explanation += (
            f" Minus a {rejection_penalty_value:.0f}-point penalty for prior analyst"
            " rejection(s) of this exact candidate."
        )
    missing = [key for key in components if key not in available]
    if missing:
        explanation += f" No {', '.join(missing)} evidence was available for this record."

    return ConfidenceResult(
        overall_confidence=round(float(overall), 1),
        name_score=name_score,
        district_score=district_score,
        region_score=region_score,
        spatial_score=spatial_score,
        historical_score=historical_score,
        semantic_score=semantic_score,
        rejection_penalty=rejection_penalty_value,
        explanation=explanation,
    )
