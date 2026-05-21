import logging

from src.data.news_data import NewsData

logger = logging.getLogger(__name__)


def score_news_sentiment(fund_news: NewsData, sector_news: NewsData, market_sentiment: float = 50.0) -> float:
    """Score news and sentiment (dimension 5, weight 0.10)."""
    scores = []
    weights = []

    # Market sentiment (25%)
    market_score = market_sentiment / 10.0 if 0 <= market_sentiment <= 100 else 5.0
    scores.append(market_score)
    weights.append(0.25)

    # Fund-specific news (40%)
    if fund_news.error:
        scores.append(5.0)
    else:
        scores.append(fund_news.sentiment_score)
    weights.append(0.40)

    # Sector news (25%)
    if sector_news.error:
        scores.append(5.0)
    else:
        scores.append(sector_news.sentiment_score)
    weights.append(0.25)

    # News volume (10%) - higher volume with positive sentiment = momentum
    if not sector_news.error and sector_news.total_count > 0:
        score = min(sector_news.total_count / 5.0 * 5, 10.0)
        scores.append(score)
        weights.append(0.10)

    if not scores:
        return 5.0

    total_weight = sum(weights)
    if total_weight > 0:
        weights = [w / total_weight for w in weights]

    return sum(s * w for s, w in zip(scores, weights))
