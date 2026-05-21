import logging
from typing import Optional

from src.data.fund_nav import FundNAVData

logger = logging.getLogger(__name__)


def _normalize(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi] and map to [0, 10]."""
    clamped = max(lo, min(hi, value))
    return 10.0 * (clamped - lo) / (hi - lo)


def score_nav_performance(nav: FundNAVData) -> float:
    """Score NAV performance (dimension 1, weight 0.25)."""
    if nav.error:
        return 5.0

    scores = []
    weights = []

    if nav.return_1w is not None:
        scores.append(_normalize(nav.return_1w, -5.0, 5.0))
        weights.append(0.35)

    if nav.return_1m is not None:
        scores.append(_normalize(nav.return_1m, -10.0, 10.0))
        weights.append(0.30)

    if nav.return_3m is not None:
        scores.append(_normalize(nav.return_3m, -15.0, 15.0))
        weights.append(0.15)

    if nav.max_drawdown_1m is not None:
        scores.append(_normalize(-nav.max_drawdown_1m, -10.0, 0.0))
        weights.append(0.10)

    if nav.volatility_annual is not None:
        # Lower volatility = higher score for short-term holding
        scores.append(_normalize(-nav.volatility_annual, -0.5, 0.0))
        weights.append(0.10)

    if not scores:
        return 5.0

    total_weight = sum(weights)
    if total_weight > 0:
        weights = [w / total_weight for w in weights]

    return sum(s * w for s, w in zip(scores, weights))
