import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

import akshare as ak

from src.data.fetcher import safe_fetch

logger = logging.getLogger(__name__)


@dataclass
class FundHoldingsData:
    fund_code: str
    fund_name: str
    top10_stocks: list[dict] = field(default_factory=list)  # [{name, code, weight_pct}]
    sector: str = ""
    sector_purity_pct: float = 0.0
    top3_concentration_pct: float = 0.0
    sector_alignment_score: float = 0.0
    error: Optional[str] = None


def fetch_fund_holdings(fund_code: str, fund_name: str = "", sector: str = "") -> FundHoldingsData:
    """Fetch top-10 holdings and compute sector alignment."""
    result = FundHoldingsData(fund_code=fund_code, fund_name=fund_name, sector=sector)

    try:
        df = safe_fetch(
            ak.fund_portfolio_hold_em,
            symbol=fund_code,
            date="2025",
            cache_ttl_seconds=3600,
        )

        if df is None or df.empty:
            result.error = "持仓数据不可用"
            return result

        df.columns = [str(c) for c in df.columns]

        stock_name_col = None
        weight_col = None
        for c in df.columns:
            if "股票名称" in c:
                stock_name_col = c
            if "占净值比例" in c or "持仓占比" in c:
                weight_col = c

        if stock_name_col is None or weight_col is None:
            result.error = f"持仓列名未识别, columns={df.columns.tolist()}"
            return result

        top10 = []
        total_weight = 0.0
        for _, row in df.head(10).iterrows():
            name = str(row[stock_name_col]) if pd.notna(row[stock_name_col]) else ""
            weight = pd.to_numeric(row[weight_col], errors="coerce")
            weight = float(weight) if pd.notna(weight) else 0.0
            top10.append({"name": name, "code": "", "weight_pct": weight})
            total_weight += weight

        result.top10_stocks = top10

        if len(top10) >= 3:
            result.top3_concentration_pct = sum(s["weight_pct"] for s in top10[:3])

        result.sector_purity_pct = min(total_weight, 100.0)

    except Exception as e:
        logger.error("fetch_fund_holdings(%s): %s", fund_code, e)
        result.error = str(e)

    return result
