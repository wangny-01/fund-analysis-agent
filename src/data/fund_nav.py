import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

import akshare as ak

from config.settings import TRADING_DAYS_1W, TRADING_DAYS_1M, TRADING_DAYS_3M, TRADING_DAYS_PER_YEAR
from src.data.fetcher import safe_fetch

logger = logging.getLogger(__name__)


@dataclass
class FundNAVData:
    fund_code: str
    fund_name: str
    nav_history: pd.DataFrame = field(default_factory=pd.DataFrame)
    return_1w: Optional[float] = None
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    max_drawdown_1m: Optional[float] = None
    volatility_annual: Optional[float] = None
    current_nav: Optional[float] = None
    error: Optional[str] = None


def fetch_fund_nav(fund_code: str, fund_name: str = "") -> FundNAVData:
    """Fetch NAV history and compute performance metrics for a single fund."""
    result = FundNAVData(fund_code=fund_code, fund_name=fund_name)

    try:
        df = safe_fetch(
            ak.fund_open_fund_info_em,
            symbol=fund_code,
            indicator="单位净值走势",
            period="日",
            cache_ttl_seconds=600,
        )

        if df is None or df.empty:
            result.error = "NAV数据不可用"
            return result

        df.columns = [str(c) for c in df.columns]
        date_col = None
        nav_col = None
        for c in df.columns:
            if "日期" in c or "时间" in c:
                date_col = c
            if "单位净值" in c:
                nav_col = c

        if date_col is None or nav_col is None:
            result.error = f"NAV列名未识别, columns={df.columns.tolist()}"
            return result

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df[nav_col] = pd.to_numeric(df[nav_col], errors="coerce")
        df = df.dropna(subset=[date_col, nav_col])
        df = df.sort_values(date_col).reset_index(drop=True)

        if len(df) < TRADING_DAYS_3M:
            result.error = f"NAV数据不足({len(df)}条,需要>=66条)"
            return result

        result.nav_history = df

        nav_series = df[nav_col].values
        result.current_nav = float(nav_series[-1])

        def _return_from_end(offset: int) -> float:
            if len(nav_series) <= offset:
                return float((nav_series[-1] / nav_series[0] - 1) * 100)
            return float((nav_series[-1] / nav_series[-(1 + offset)] - 1) * 100)

        result.return_1w = _return_from_end(TRADING_DAYS_1W)
        result.return_1m = _return_from_end(TRADING_DAYS_1M)
        result.return_3m = _return_from_end(TRADING_DAYS_3M)

        # 1-month max drawdown
        lookback = TRADING_DAYS_1M
        recent = nav_series[-lookback:] if len(nav_series) >= lookback else nav_series
        peak = recent[0]
        max_dd = 0.0
        for v in recent:
            if v > peak:
                peak = v
            dd = (v / peak - 1) * 100
            if dd < max_dd:
                max_dd = dd
        result.max_drawdown_1m = max_dd

        # Annualized volatility (1-month lookback)
        daily_returns = np.diff(nav_series[-lookback:]) / nav_series[-lookback:-1]
        if len(daily_returns) > 1:
            result.volatility_annual = float(np.std(daily_returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))

    except Exception as e:
        logger.error("fetch_fund_nav(%s) failed: %s", fund_code, e)
        result.error = str(e)

    return result


def fetch_current_nav(fund_code: str) -> Optional[float]:
    """Quick fetch of current NAV for redemption monitoring."""
    try:
        df = safe_fetch(
            ak.fund_open_fund_info_em,
            symbol=fund_code,
            indicator="单位净值走势",
            period="日",
            cache_ttl_seconds=300,
        )
        if df is None or df.empty:
            return None
        df.columns = [str(c) for c in df.columns]
        nav_col = None
        for c in df.columns:
            if "单位净值" in c:
                nav_col = c
        if nav_col is None:
            return None
        navs = pd.to_numeric(df[nav_col], errors="coerce").dropna()
        if navs.empty:
            return None
        return float(navs.values[-1])
    except Exception as e:
        logger.error("fetch_current_nav(%s): %s", fund_code, e)
        return None
