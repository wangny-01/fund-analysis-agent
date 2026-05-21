import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

import akshare as ak

from config.settings import SECTOR_LIST
from src.data.fetcher import safe_fetch

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    sector: str
    sector_return_1w: Optional[float] = None
    sector_return_1m: Optional[float] = None
    sector_return_3m: Optional[float] = None
    sector_trend: str = "震荡"   # "上升", "震荡", "下降"
    sector_ma5: Optional[float] = None
    sector_ma20: Optional[float] = None
    capital_flow_direction: str = "净流出"
    capital_flow_score: float = 5.0
    relative_strength_vs_300: Optional[float] = None
    error: Optional[str] = None


@dataclass
class MarketSnapshot:
    sectors: dict[str, MarketData] = field(default_factory=dict)
    north_bound_flow_5d: Optional[float] = None
    csi300_return_1w: Optional[float] = None
    csi300_return_1m: Optional[float] = None
    macro_highlights: list[str] = field(default_factory=list)
    top_flow_sectors: list[tuple[str, float]] = field(default_factory=list)


def _fetch_sector_index(sector: str, boards: list[str]) -> MarketData:
    """Fetch sector-level market data by aggregating sub-industry board data."""
    result = MarketData(sector=sector)

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")

        all_closes = []
        board_count = 0

        for board in boards:
            df = safe_fetch(
                ak.stock_board_industry_hist_em,
                symbol=board,
                period="日k",
                start_date=start_date,
                end_date=end_date,
                cache_ttl_seconds=1800,
            )

            if df is None or df.empty:
                continue

            df.columns = [str(c) for c in df.columns]
            close_col = None
            for c in df.columns:
                if "收盘" in c:
                    close_col = c

            if close_col is None:
                continue

            closes = pd.to_numeric(df[close_col], errors="coerce").dropna()
            if len(closes) >= 22:
                all_closes.append(closes.values)
                board_count += 1

        if not all_closes:
            result.error = "无法获取板块指数数据"
            return result

        # Average across sub-industries
        min_len = min(len(arr) for arr in all_closes)
        trimmed = [arr[-min_len:] for arr in all_closes]
        composite = np.mean(trimmed, axis=0)

        if len(composite) >= 22:
            # Returns
            result.sector_return_1w = float((composite[-1] / composite[-6] - 1) * 100) if len(composite) >= 6 else None
            result.sector_return_1m = float((composite[-1] / composite[-22] - 1) * 100)
            if len(composite) >= 66:
                result.sector_return_3m = float((composite[-1] / composite[-66] - 1) * 100)

            # Moving averages for trend
            ma5 = float(np.mean(composite[-5:]))
            ma20 = float(np.mean(composite[-20:]))
            result.sector_ma5 = ma5
            result.sector_ma20 = ma20

            if ma5 > ma20 * 1.01:
                result.sector_trend = "上升"
            elif ma5 < ma20 * 0.99:
                result.sector_trend = "下降"
            else:
                result.sector_trend = "震荡"

            # Volume trend for capital flow proxy
            if len(composite) >= 11:
                recent_vol = np.mean(composite[-5:])
                prior_vol = np.mean(composite[-11:-5])
                if recent_vol > prior_vol * 1.05:
                    result.capital_flow_direction = "净流入"
                    result.capital_flow_score = 7.0
                elif recent_vol < prior_vol * 0.95:
                    result.capital_flow_direction = "净流出"
                    result.capital_flow_score = 3.0
                else:
                    result.capital_flow_direction = "平衡"
                    result.capital_flow_score = 5.0
        else:
            result.error = f"数据不足({len(composite)}条)"

    except Exception as e:
        logger.error("fetch_sector_index(%s): %s", sector, e)
        result.error = str(e)

    return result


def fetch_market_data(sector_boards: dict[str, list[str]]) -> MarketSnapshot:
    """Fetch market data for all sectors plus macro indicators."""
    snapshot = MarketSnapshot()

    for sector in SECTOR_LIST:
        boards = sector_boards.get(sector, [])
        if boards:
            snapshot.sectors[sector] = _fetch_sector_index(sector, boards)
        else:
            snapshot.sectors[sector] = MarketData(sector=sector, error="无板块映射")

    # CSI 300 for relative strength
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        csi300 = safe_fetch(
            ak.stock_zh_index_daily_em,
            symbol="sh000300",
            start_date=start_date,
            end_date=end_date,
            cache_ttl_seconds=1800,
        )

        if csi300 is not None and not csi300.empty:
            csi300.columns = [str(c) for c in csi300.columns]
            close_col = None
            for c in csi300.columns:
                if "close" in c.lower() or "收盘" in c:
                    close_col = c
            if close_col:
                closes = pd.to_numeric(csi300[close_col], errors="coerce").dropna().values
                if len(closes) >= 22:
                    snapshot.csi300_return_1w = float((closes[-1] / closes[-6] - 1) * 100) if len(closes) >= 6 else None
                    snapshot.csi300_return_1m = float((closes[-1] / closes[-22] - 1) * 100)

                    # Sector relative strength
                    for sector, md in snapshot.sectors.items():
                        if md.sector_return_1m is not None and snapshot.csi300_return_1m is not None:
                            md.relative_strength_vs_300 = md.sector_return_1m - snapshot.csi300_return_1m
    except Exception as e:
        logger.error("fetch_csi300: %s", e)

    # North-bound capital flow
    try:
        north = safe_fetch(
            ak.stock_hsgt_north_net_flow_in_em,
            indicator="沪股通",
            cache_ttl_seconds=1800,
        )

        if north is not None and not north.empty:
            north.columns = [str(c) for c in north.columns]
            net_col = None
            for c in north.columns:
                if "净流入" in c or "净买卖" in c:
                    net_col = c
            if net_col:
                flows = pd.to_numeric(north[net_col], errors="coerce").dropna()
                if len(flows) >= 5:
                    snapshot.north_bound_flow_5d = float(flows.tail(5).sum())
    except Exception as e:
        logger.error("fetch_north_bound: %s", e)

    # Top flow sectors
    flow_data = []
    for sector, md in snapshot.sectors.items():
        if md.sector_return_1w is not None:
            flow_data.append((sector, md.sector_return_1w))
    flow_data.sort(key=lambda x: x[1], reverse=True)
    snapshot.top_flow_sectors = flow_data[:3]

    return snapshot
