import logging

from src.data.fund_holdings import FundHoldingsData

logger = logging.getLogger(__name__)


def score_holdings_quality(holdings: FundHoldingsData) -> float:
    """Score holdings quality (dimension 2, weight 0.15)."""
    if holdings.error or not holdings.top10_stocks:
        return 5.0

    scores = []
    weights = []

    # Sector purity: % of holdings matching target sector (higher = better up to a point)
    purity = holdings.sector_purity_pct
    if purity > 60:
        scores.append(8.0 + min((purity - 60) / 40 * 2.0, 2.0))
    elif purity > 30:
        scores.append(5.0 + (purity - 30) / 30 * 3.0)
    else:
        scores.append(max(purity / 30 * 5.0, 0.0))
    weights.append(0.40)

    # Concentration stability: top3 25-45% is ideal
    top3 = holdings.top3_concentration_pct
    if 25 <= top3 <= 45:
        scores.append(9.0)
    elif 15 <= top3 <= 60:
        scores.append(6.0)
    elif top3 > 60:
        scores.append(3.0)
    else:
        scores.append(4.0)
    weights.append(0.30)

    # Diversification: moderate number of holdings
    n_stocks = len(holdings.top10_stocks)
    if n_stocks >= 8:
        scores.append(8.0)
    elif n_stocks >= 5:
        scores.append(6.0)
    else:
        scores.append(4.0)
    weights.append(0.30)

    return sum(s * w for s, w in zip(scores, weights))
