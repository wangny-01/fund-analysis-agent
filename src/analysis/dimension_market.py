import logging

from src.data.market_data import MarketData

logger = logging.getLogger(__name__)


def _normalize(value: float, lo: float, hi: float) -> float:
    clamped = max(lo, min(hi, value))
    return 10.0 * (clamped - lo) / (hi - lo)


def score_market_policy(market: MarketData, north_bound_5d: float = 0.0) -> float:
    """Score market and policy environment (dimension 4, weight 0.15)."""
    if market.error:
        return 5.0

    scores = []
    weights = []

    # Sector trend
    if market.sector_trend == "上升":
        scores.append(8.0)
    elif market.sector_trend == "震荡":
        scores.append(5.5)
    else:
        scores.append(2.5)
    weights.append(0.35)

    # Capital flow
    if market.capital_flow_direction == "净流入":
        scores.append(7.5)
    elif market.capital_flow_direction == "平衡":
        scores.append(5.0)
    else:
        scores.append(3.0)
    weights.append(0.30)

    # Relative strength vs CSI 300
    if market.relative_strength_vs_300 is not None:
        scores.append(_normalize(market.relative_strength_vs_300, -5.0, 5.0))
        weights.append(0.20)

    # Sector return trajectory (1w return)
    if market.sector_return_1w is not None:
        scores.append(_normalize(market.sector_return_1w, -3.0, 3.0))
        weights.append(0.15)

    if not scores:
        return 5.0

    total_weight = sum(weights)
    if total_weight > 0:
        weights = [w / total_weight for w in weights]

    return sum(s * w for s, w in zip(scores, weights))
