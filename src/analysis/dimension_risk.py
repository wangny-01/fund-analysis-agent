import logging
from typing import Optional

import numpy as np
import pandas as pd

from config.settings import RISK_FREE_RATE, TRADING_DAYS_PER_YEAR
from src.data.fund_nav import FundNAVData

logger = logging.getLogger(__name__)


def _normalize(value: float, lo: float, hi: float) -> float:
    clamped = max(lo, min(hi, value))
    return 10.0 * (clamped - lo) / (hi - lo)


def _compute_sharpe(daily_returns: np.ndarray, rf_daily: float = 0.0) -> Optional[float]:
    if len(daily_returns) < 2:
        return None
    excess = daily_returns - rf_daily
    mean = np.mean(excess)
    std = np.std(excess, ddof=1)
    if std == 0:
        return None
    return float((mean / std) * np.sqrt(TRADING_DAYS_PER_YEAR))


def _compute_beta(fund_returns: np.ndarray, market_returns: np.ndarray) -> Optional[float]:
    min_len = min(len(fund_returns), len(market_returns))
    if min_len < 2:
        return None
    f = fund_returns[-min_len:]
    m = market_returns[-min_len:]
    cov = np.cov(f, m)
    if cov[1, 1] == 0:
        return None
    return float(cov[0, 1] / cov[1, 1])


def _compute_alpha(
    fund_returns: np.ndarray,
    market_returns: np.ndarray,
    beta: float,
    rf_daily: float = 0.0,
) -> Optional[float]:
    min_len = min(len(fund_returns), len(market_returns))
    if min_len < 2:
        return None
    f = fund_returns[-min_len:]
    m = market_returns[-min_len:]
    fund_mean = np.mean(f) - rf_daily
    market_mean = np.mean(m) - rf_daily
    return float((fund_mean - beta * market_mean) * TRADING_DAYS_PER_YEAR)


def score_risk_metrics(nav: FundNAVData, market_nav: Optional[FundNAVData] = None) -> float:
    """Score risk-adjusted returns (dimension 3, weight 0.20)."""
    if nav.error or nav.nav_history.empty:
        return 5.0

    try:
        navs = nav.nav_history
        nav_col = None
        for c in navs.columns:
            if "单位净值" in str(c):
                nav_col = str(c)
        if nav_col is None:
            return 5.0

        nav_vals = pd.to_numeric(navs[nav_col], errors="coerce").dropna().values
        if len(nav_vals) < 22:
            return 5.0

        daily_returns = np.diff(nav_vals) / nav_vals[:-1]
        rf_daily = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR

        scores = []
        weights = []

        # Sharpe ratio
        sharpe = _compute_sharpe(daily_returns, rf_daily)
        if sharpe is not None:
            scores.append(_normalize(sharpe, -1.0, 3.0))
            weights.append(0.35)

        # Beta and Alpha (if market data available)
        market_returns = None
        if market_nav is not None and not market_nav.error and not market_nav.nav_history.empty:
            mnavs = market_nav.nav_history
            for c in mnavs.columns:
                if "收盘" in str(c):
                    m_vals = pd.to_numeric(mnavs[str(c)], errors="coerce").dropna().values
                    market_returns = np.diff(m_vals) / m_vals[:-1]
                    break

        if market_returns is not None:
            beta = _compute_beta(daily_returns, market_returns)
            if beta is not None:
                alpha = _compute_alpha(daily_returns, market_returns, beta, rf_daily)
                if alpha is not None:
                    scores.append(_normalize(alpha, -0.1, 0.3))
                    weights.append(0.30)

                # Beta penalty: ideal is 0.7-1.2 for short-term holding
                if 0.7 <= beta <= 1.2:
                    beta_score = 9.0
                elif 0.3 <= beta <= 2.0:
                    beta_score = 5.0 + (1.0 - abs(beta - 1.0)) * 4
                else:
                    beta_score = 2.0
                scores.append(beta_score)
                weights.append(0.20)

        # Max drawdown from NAV (already in nav data as negative)
        if nav.max_drawdown_1m is not None:
            dd_score = _normalize(-nav.max_drawdown_1m, -10.0, 0.0)
            scores.append(dd_score)
            weights.append(0.15)

        if not scores:
            return 5.0

        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]

        return sum(s * w for s, w in zip(scores, weights))

    except Exception as e:
        logger.error("score_risk_metrics(%s): %s", nav.fund_code, e)
        return 5.0
