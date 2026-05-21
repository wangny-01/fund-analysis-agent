import logging
from dataclasses import dataclass, field
from typing import Optional

import akshare as ak
import pandas as pd

from src.data.fetcher import safe_fetch

logger = logging.getLogger(__name__)

POSITIVE_KEYWORDS = [
    "增持", "增长", "利好", "上升", "突破", "改善", "政策支持",
    "加仓", "业绩预增", "净利润增长", "营收增长", "超预期",
    "技术突破", "新品发布", "获批", "创新", "行业龙头",
]
NEGATIVE_KEYWORDS = [
    "减持", "下跌", "亏损", "风险", "违规", "处罚", "踩雷",
    "下滑", "下降", "萎缩", "败退", "业绩预亏", "退市风险",
    "清盘", "暴雷", "违约", "调查", "诉讼", "限售",
]


@dataclass
class NewsData:
    sector: str = ""
    fund_code: str = ""
    sentiment_score: float = 5.0
    positive_count: int = 0
    negative_count: int = 0
    total_count: int = 0
    headlines: list[str] = field(default_factory=list)
    market_sentiment_index: Optional[float] = None
    error: Optional[str] = None


def _classify_sentiment(text: str) -> str:
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    return "neutral"


def fetch_market_sentiment() -> Optional[float]:
    """Fetch overall market sentiment index."""
    try:
        df = safe_fetch(ak.index_news_sentiment_scope, cache_ttl_seconds=1800)
        if df is not None and not df.empty:
            df.columns = [str(c) for c in df.columns]
            for c in df.columns:
                if "sentiment" in c.lower() or "情绪" in c:
                    val = pd.to_numeric(df[c].iloc[-1], errors="coerce")
                    if pd.notna(val):
                        return float(val)
    except Exception as e:
        logger.error("fetch_market_sentiment: %s", e)
    return None


def fetch_sector_news(sector: str, keywords: list[str]) -> NewsData:
    """Fetch sector-related news and compute sentiment."""
    result = NewsData(sector=sector)

    try:
        df = safe_fetch(
            ak.stock_info_global_cls,
            symbol="全部",
            cache_ttl_seconds=600,
        )

        if df is None or df.empty:
            result.error = "新闻数据不可用"
            return result

        df.columns = [str(c) for c in df.columns]

        title_col = content_col = None
        for c in df.columns:
            if "标题" in c or "title" in c.lower():
                title_col = c
            if "内容" in c or "content" in c.lower():
                content_col = c

        if title_col is None:
            result.error = "新闻列名未识别"
            return result

        # Filter for sector-relevant news
        for _, row in df.head(100).iterrows():
            title = str(row[title_col]) if pd.notna(row[title_col]) else ""
            body = str(row[content_col]) if content_col and pd.notna(row[content_col]) else ""
            full_text = title + " " + body

            matched = False
            for kw in keywords:
                if kw in full_text:
                    matched = True
                    break

            if not matched:
                continue

            result.total_count += 1
            sentiment = _classify_sentiment(full_text)
            if sentiment == "positive":
                result.positive_count += 1
            elif sentiment == "negative":
                result.negative_count += 1

            if len(result.headlines) < 10:
                result.headlines.append(title[:80])

        if result.total_count > 0:
            result.sentiment_score = (result.positive_count / result.total_count) * 10

    except Exception as e:
        logger.error("fetch_sector_news(%s): %s", sector, e)
        result.error = str(e)

    return result


def fetch_fund_news(fund_code: str, fund_name: str = "") -> NewsData:
    """Fetch fund-specific news using fund name/sector keywords."""
    result = NewsData(fund_code=fund_code)

    try:
        df = safe_fetch(
            ak.stock_info_global_cls,
            symbol="全部",
            cache_ttl_seconds=600,
        )

        if df is None or df.empty:
            result.error = "新闻数据不可用"
            return result

        df.columns = [str(c) for c in df.columns]

        title_col = None
        for c in df.columns:
            if "标题" in c or "title" in c.lower():
                title_col = c

        if title_col is None:
            return result

        for _, row in df.head(100).iterrows():
            title = str(row[title_col]) if pd.notna(row[title_col]) else ""

            # Match fund name or code
            if fund_name and fund_name[:4] in title:
                result.total_count += 1
            elif fund_code in title:
                result.total_count += 1
            else:
                continue

            sentiment = _classify_sentiment(title)
            if sentiment == "positive":
                result.positive_count += 1
            elif sentiment == "negative":
                result.negative_count += 1

            if len(result.headlines) < 5:
                result.headlines.append(title[:80])

        if result.total_count > 0:
            result.sentiment_score = (result.positive_count / max(result.total_count, 1)) * 10

    except Exception as e:
        logger.error("fetch_fund_news(%s): %s", fund_code, e)
        result.error = str(e)

    return result
