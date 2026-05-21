import logging

from src.data.fund_manager import FundManagerData

logger = logging.getLogger(__name__)


def _normalize(value: float, lo: float, hi: float) -> float:
    clamped = max(lo, min(hi, value))
    return 10.0 * (clamped - lo) / (hi - lo)


def score_manager_quality(manager: FundManagerData) -> float:
    """Score fund manager quality (dimension 6, weight 0.15)."""
    if manager.error:
        return 5.0

    scores = []
    weights = []

    # Tenure score
    tenure = manager.tenure_years
    if tenure > 8:
        scores.append(9.5)
    elif tenure > 5:
        scores.append(8.0)
    elif tenure > 3:
        scores.append(6.5)
    elif tenure > 1:
        scores.append(5.0)
    elif tenure > 0:
        scores.append(3.0)
    else:
        scores.append(2.0)
    weights.append(0.25)

    # AUM management: moderate size is better for active funds
    # But we don't have reliable AUM data from akshare, so use fund count as proxy
    fund_count = manager.funds_managed_count
    if 0 < fund_count <= 5:
        aum_score = 8.0
    elif fund_count <= 10:
        aum_score = 6.0
    elif fund_count > 10:
        aum_score = 4.0
    else:
        aum_score = 5.0
    scores.append(aum_score)
    weights.append(0.15)

    # Historical return (if available)
    if manager.historical_annual_return is not None:
        scores.append(_normalize(manager.historical_annual_return, -5.0, 25.0))
        weights.append(0.30)
    else:
        # Use tenure as backup signal
        scores.append(5.0)
        weights.append(0.30)

    # Style stability: tenure is the best proxy without detailed data
    scores.append(5.0 if manager.recent_change else 8.0)
    weights.append(0.20)

    # Recent change penalty
    if manager.recent_change:
        scores.append(2.0)
        weights.append(0.10)
    else:
        scores.append(8.0)
        weights.append(0.10)

    total_weight = sum(weights)
    if total_weight > 0:
        weights = [w / total_weight for w in weights]

    return sum(s * w for s, w in zip(scores, weights))
