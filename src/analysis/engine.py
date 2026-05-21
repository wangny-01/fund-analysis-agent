import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import DIMENSION_WEIGHTS, GREEN_THRESHOLD, YELLOW_THRESHOLD
from src.analysis.dimension_holdings import score_holdings_quality
from src.analysis.dimension_manager import score_manager_quality
from src.analysis.dimension_market import score_market_policy
from src.analysis.dimension_nav import score_nav_performance
from src.analysis.dimension_news import score_news_sentiment
from src.analysis.dimension_risk import score_risk_metrics
from src.data.fund_holdings import FundHoldingsData
from src.data.fund_manager import FundManagerData
from src.data.fund_nav import FundNAVData
from src.data.market_data import MarketData
from src.data.news_data import NewsData

logger = logging.getLogger(__name__)


@dataclass
class FundScore:
    fund_code: str
    fund_name: str
    sector: str
    total_score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    recommendation_level: str = "回避"
    recommended_hold_days: int = 7
    nav_data: Optional[FundNAVData] = None
    holdings_data: Optional[FundHoldingsData] = None
    manager_data: Optional[FundManagerData] = None
    market_data: Optional[MarketData] = None
    fund_news: Optional[NewsData] = None
    sector_news: Optional[NewsData] = None


def score_fund(
    fund_code: str,
    fund_name: str,
    sector: str,
    nav: FundNAVData,
    holdings: FundHoldingsData,
    manager: FundManagerData,
    market: MarketData,
    fund_news: NewsData,
    sector_news: NewsData,
    market_sentiment: float = 50.0,
) -> FundScore:
    """Run all 6 dimension scorers and compute weighted composite."""

    fs = FundScore(
        fund_code=fund_code,
        fund_name=fund_name,
        sector=sector,
        nav_data=nav,
        holdings_data=holdings,
        manager_data=manager,
        market_data=market,
        fund_news=fund_news,
        sector_news=sector_news,
    )

    # Phase 1: Compute raw dimension scores
    d1 = score_nav_performance(nav)
    d2 = score_holdings_quality(holdings)
    d3 = score_risk_metrics(nav)
    d4 = score_market_policy(market)
    d5 = score_news_sentiment(fund_news, sector_news, market_sentiment)
    d6 = score_manager_quality(manager)

    fs.dimension_scores = {
        "nav_performance": round(d1, 1),
        "holdings_quality": round(d2, 1),
        "risk_metrics": round(d3, 1),
        "market_policy": round(d4, 1),
        "news_sentiment": round(d5, 1),
        "manager_quality": round(d6, 1),
    }

    # Phase 2: Weighted composite
    total = 0.0
    for dim_name, score in fs.dimension_scores.items():
        total += score * DIMENSION_WEIGHTS.get(dim_name, 0.0)

    fs.total_score = round(total, 1)

    # Phase 3: Recommendation level
    if fs.total_score >= GREEN_THRESHOLD and market.sector_trend != "下降":
        fs.recommendation_level = "强烈推荐"
    elif fs.total_score >= YELLOW_THRESHOLD:
        fs.recommendation_level = "谨慎关注"
    else:
        fs.recommendation_level = "回避"

    if market.sector_trend == "下降" and fs.recommendation_level == "强烈推荐":
        fs.recommendation_level = "谨慎关注"

    fs.recommended_hold_days = 7 if fs.recommendation_level == "强烈推荐" else 9

    return fs
