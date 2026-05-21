import logging
from datetime import datetime
from typing import Optional

from src.analysis.engine import FundScore
from src.analysis.redemption import RedemptionSignal
from src.data.market_data import MarketSnapshot
from src.data.fund_nav import FundNAVData

logger = logging.getLogger(__name__)


def _emoji_level(level: str) -> str:
    if level == "强烈推荐":
        return "🟢"
    elif level == "谨慎关注":
        return "🟡"
    return "🔴"


def _emoji_trend(trend: str) -> str:
    if trend == "上升":
        return "📈"
    elif trend == "下降":
        return "📉"
    return "📊"


def _emoji_flow(flow: str) -> str:
    if "流入" in flow:
        return "🔥"
    return "💧"


def format_recommendation_report(
    recommendations: list[FundScore],
    market_snapshot: MarketSnapshot,
) -> str:
    """Build a complete markdown weekly report matching CLAUDE.md spec."""

    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    lines = [
        f"# 📊 基金周报分析报告",
        f"**生成时间**: {now}",
        f"**分析板块**: 科技/消费/医疗/新能源/军工/金融/房地产/有色金属",
        f"---",
        "",
        "## 🎯 推荐基金清单（{0}支）".format(len(recommendations)),
        "",
    ]

    for i, fs in enumerate(recommendations, 1):
        lines.append(
            f"### {i}. {fs.fund_name} / {fs.fund_code} | "
            f"推荐评分：**{fs.total_score}/10分** | "
            f"持仓周期：**{fs.recommended_hold_days}天** | "
            f"{_emoji_level(fs.recommendation_level)} {fs.recommendation_level}"
        )

        # Recommendation reason
        nav = fs.nav_data
        reasons = []
        if nav and nav.return_1w is not None:
            reasons.append(f"近1周净值增长{nav.return_1w:.1f}%")
        if nav and nav.return_1m is not None:
            reasons.append(f"近1月增长{nav.return_1m:.1f}%")
        if fs.manager_data and fs.manager_data.manager_name:
            reasons.append(f"基金经理{fs.manager_data.manager_name}管理经验超{fs.manager_data.tenure_years:.0f}年")
        if fs.market_data:
            reasons.append(f"{fs.sector}板块{fs.market_data.sector_trend}趋势")

        reason_text = "，".join(reasons) if reasons else "综合评分优秀"
        lines.append(f"- **推荐理由**: {reason_text}。综合维度评分{fs.total_score}分，在同类型基金中表现突出。")

        # Key data
        key_data_parts = []
        if nav:
            if nav.return_1w is not None:
                key_data_parts.append(f"近1周{nav.return_1w:+.1f}%")
            if nav.return_1m is not None:
                key_data_parts.append(f"近1月{nav.return_1m:+.1f}%")
        sharpe = fs.dimension_scores.get("risk_metrics", "-")
        dd_str = f"{nav.max_drawdown_1m:.1f}%" if nav and nav.max_drawdown_1m is not None else "-"
        key_data_parts.append(f"夏普维度{sharpe}分")
        key_data_parts.append(f"最大回撤{dd_str}")
        lines.append(f"- 📊 **关键数据**: {' | '.join(key_data_parts)}")

        # Top holdings
        if fs.holdings_data and fs.holdings_data.top10_stocks:
            top3 = fs.holdings_data.top10_stocks[:3]
            top3_str = " / ".join(
                f"{s['name']}({s['weight_pct']:.1f}%)" for s in top3
            )
            lines.append(f"- 🏢 **重仓股TOP3**: {top3_str}")

        # Sector trend
        if fs.market_data:
            trend = fs.market_data.sector_trend
            flow = fs.market_data.capital_flow_direction
            lines.append(
                f"- 🎯 **板块趋势**: {_emoji_trend(trend)} {trend} | "
                f"**资金流向**: {_emoji_flow(flow)} {flow}"
            )

        # Risk warning
        risk_warnings = []
        if nav and nav.max_drawdown_1m is not None and nav.max_drawdown_1m < -3:
            risk_warnings.append(f"近1月最大回撤{nav.max_drawdown_1m:.1f}%，短期波动较大")
        if fs.market_data and fs.market_data.sector_trend == "下降":
            risk_warnings.append(f"{fs.sector}板块处于下降通道")
        if not risk_warnings:
            risk_warnings.append("短期市场波动风险，建议严格按照持有周期操作")
        lines.append(f"- ⚠️ **风险提示**: {'; '.join(risk_warnings)}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Market Environment
    lines.append("## 🌍 市场环境快报")
    lines.append("")

    macro_items = [
        "- **本周宏观焦点**: 关注央行公开市场操作、北向资金流向、行业政策动态",
    ]
    if market_snapshot.north_bound_flow_5d is not None:
        direction = "净流入" if market_snapshot.north_bound_flow_5d > 0 else "净流出"
        macro_items.append(f"- **北向资金5日**: {direction} {abs(market_snapshot.north_bound_flow_5d):.1f}亿元")
    lines.extend(macro_items)

    lines.append("")
    if market_snapshot.top_flow_sectors:
        top_flows = market_snapshot.top_flow_sectors
        flow_str = " / ".join(f"{s}({v:+.1f}%)" for s, v in top_flows)
        lines.append(f"- **行业资金流向TOP3**: {flow_str}")

    lines.append(f"- **CSI 300**: 近1周{market_snapshot.csi300_return_1w:+.1f}% | 近1月{market_snapshot.csi300_return_1m:+.1f}%" if market_snapshot.csi300_return_1w is not None else "")

    lines.append("")
    lines.append("---")
    lines.append(f"*本报告由基金分析Agent自动生成，仅供参考，不构成投资建议。*")

    return "\n".join(lines)


def format_redemption_alert(
    fund_code: str,
    fund_name: str,
    signals: list[RedemptionSignal],
    current_pnl: float,
    holding_days: int,
) -> Optional[str]:
    """Build a redemption alert message. Returns None if no critical/high signals."""

    critical = [s for s in signals if s.triggered and s.priority == "CRITICAL"]
    high = [s for s in signals if s.triggered and s.priority == "HIGH"]
    medium = [s for s in signals if s.triggered and s.priority == "MEDIUM"]

    if not (critical or high or medium):
        return None

    lines = [
        f"## 🚨 赎回提醒 - {fund_name} ({fund_code})",
        "",
        f"**当前收益**: {current_pnl:+.2f}% | **持有天数**: {holding_days}天",
        "",
    ]

    if critical:
        lines.append("### 🔴 危急信号")
        for s in critical:
            lines.append(f"- **{s.signal_name}** → {s.action}")

    if high:
        lines.append("### 🟠 高度关注")
        for s in high:
            lines.append(f"- **{s.signal_name}** → {s.action}")

    if medium:
        lines.append("### 🟡 提醒")
        for s in medium:
            lines.append(f"- **{s.signal_name}** → {s.action}")

    return "\n".join(lines)


def format_held_funds_tracking(
    holdings: list[dict],
    nav_cache: dict[str, FundNAVData],
) -> str:
    """Format the held funds tracking table section."""

    if not holdings:
        return "## 📋 持有中基金跟踪\n\n当前无持有中基金。\n"

    lines = [
        "## 📋 持有中基金跟踪",
        "",
        "| 基金名称 | 当前收益 | 距最大回撤 | 赎回建议 |",
        "|----------|---------|-----------|---------|",
    ]

    for h in holdings:
        name = h.get("fund_name", h.get("fund_code", ""))
        code = h.get("fund_code", "")
        purchase_nav = h.get("purchase_nav", 1.0)
        nav_data = nav_cache.get(code)
        current_nav = nav_data.current_nav if nav_data else None

        if current_nav and purchase_nav > 0:
            pnl = (current_nav / purchase_nav - 1) * 100
            pnl_str = f"{pnl:+.2f}%"
        else:
            pnl_str = "N/A"

        dd_str = f"{nav_data.max_drawdown_1m:.1f}%" if nav_data and nav_data.max_drawdown_1m else "N/A"

        target_days = h.get("recommended_hold_days", 7)
        elapsed = h.get("holding_days", 0)
        if elapsed >= target_days:
            suggestion = "建议止盈/止损"
        elif elapsed >= target_days - 2:
            suggestion = "即将到期，关注"
        else:
            suggestion = "继续持有"

        lines.append(f"| {name} / {code} | {pnl_str} | {dd_str} | {suggestion} |")

    return "\n".join(lines) + "\n"
