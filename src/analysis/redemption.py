import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from config.settings import MAX_HOLD_DAYS
from src.data.fund_nav import FundNAVData
from src.data.market_data import MarketData

logger = logging.getLogger(__name__)


@dataclass
class RedemptionSignal:
    priority: str        # "CRITICAL", "HIGH", "MEDIUM"
    signal_name: str
    action: str
    triggered: bool = False


def check_redemption_signals(
    fund_code: str,
    fund_name: str,
    purchase_nav: float,
    holding_days: int,
    nav_data: Optional[FundNAVData],
    market_data: Optional[MarketData],
    previous_rank_pct: Optional[float],
    current_rank_pct: Optional[float],
    sector_negative_news: bool = False,
) -> list[RedemptionSignal]:
    """Check all 5 redemption signals and return triggered ones."""

    signals = []
    current_nav = nav_data.current_nav if nav_data else None

    if current_nav and purchase_nav > 0:
        current_pnl = (current_nav / purchase_nav - 1) * 100
    else:
        current_pnl = 0.0

    # Signal 1: Single-week drawdown > -5% → IMMEDIATE REDEMPTION
    if nav_data and nav_data.return_1w is not None:
        triggered = nav_data.return_1w < -5.0
        signals.append(RedemptionSignal(
            priority="CRITICAL",
            signal_name=f"单周回撤{nav_data.return_1w:.1f}%",
            action="立即赎回" if triggered else "",
            triggered=triggered,
        ))

    # Signal 2: 3 consecutive NAV decline days
    if nav_data and not nav_data.nav_history.empty:
        nav_col = None
        for c in nav_data.nav_history.columns:
            if "单位净值" in str(c):
                nav_col = str(c)
        if nav_col:
            nav_vals = nav_data.nav_history[nav_col].dropna().values
            decline_days = 0
            for i in range(len(nav_vals) - 1, max(0, len(nav_vals) - 10), -1):
                if i > 0 and nav_vals[i] < nav_vals[i - 1]:
                    decline_days += 1
                else:
                    if decline_days < 3:
                        decline_days = 0
                        break

            s2 = RedemptionSignal(
                priority="HIGH",
                signal_name=f"连续{decline_days}日净值下跌",
                action="",
                triggered=False,
            )

            if decline_days >= 3:
                s2.triggered = True
                if market_data and market_data.sector_trend == "下降":
                    s2.action = "建议赎回（板块转弱）"
                else:
                    s2.priority = "MEDIUM"
                    s2.action = "观望1-2日"
            signals.append(s2)

    # Signal 3: Ranking dropped from top 30% to bottom 50%
    if previous_rank_pct is not None and current_rank_pct is not None:
        triggered = previous_rank_pct < 0.30 and current_rank_pct > 0.50
        signals.append(RedemptionSignal(
            priority="HIGH",
            signal_name=f"排名从{previous_rank_pct*100:.0f}%跌至{current_rank_pct*100:.0f}%",
            action="赎回" if triggered else "",
            triggered=triggered,
        ))

    # Signal 4: Holding period >= 9 days
    if holding_days >= MAX_HOLD_DAYS:
        if current_pnl > 0:
            action = "止盈"
        else:
            action = "止损"
        signals.append(RedemptionSignal(
            priority="MEDIUM",
            signal_name=f"持有周期{holding_days}天(≥{MAX_HOLD_DAYS})",
            action=action,
            triggered=True,
        ))
    else:
        signals.append(RedemptionSignal(
            priority="MEDIUM",
            signal_name=f"持有{holding_days}天",
            action="继续持有",
            triggered=False,
        ))

    # Signal 5: Major sector-negative policy
    signals.append(RedemptionSignal(
        priority="HIGH",
        signal_name="板块利空政策",
        action="立即评估" if sector_negative_news else "",
        triggered=sector_negative_news,
    ))

    return signals
