import logging
from typing import Optional

from src.analysis.engine import FundScore
from src.data.fund_nav import FundNAVData
from config.settings import DEFAULT_HOLD_DAYS

logger = logging.getLogger(__name__)


def rank_funds(
    fund_scores: list[FundScore],
    top_n: int = 5,
) -> list[FundScore]:
    """Rank funds by composite score and return top N recommendations."""

    # Sort by total_score desc
    ranked = sorted(fund_scores, key=lambda x: x.total_score, reverse=True)

    # Deduplicate by sector (at most 1 per sector in top 5, but cross-sector is primary)
    recommendations = []
    seen_sectors: set[str] = set()

    for fs in ranked:
        if fs.recommendation_level == "回避":
            continue
        if len(recommendations) >= top_n:
            break
        # Allow same sector if there are not enough unique sectors
        if len(recommendations) < top_n:
            # Prefer sector diversity but don't force it
            if fs.sector not in seen_sectors or len(ranked) <= top_n:
                recommendations.append(fs)
                seen_sectors.add(fs.sector)

    # If we have fewer than top_n, fill from remaining
    if len(recommendations) < top_n:
        for fs in ranked:
            if fs not in recommendations and fs.recommendation_level != "回避":
                recommendations.append(fs)
            if len(recommendations) >= top_n:
                break

    return recommendations[:top_n]
