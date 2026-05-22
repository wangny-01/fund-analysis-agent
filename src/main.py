"""
Fund Analysis Agent - Main Entry Point.

Usage:
    python -m src.main --mode weekly    # Full analysis + recommendations
    python -m src.main --mode daily     # Redemption monitoring only
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml

from config.settings import (
    SECTOR_LIST,
    WATCHLIST_PATH,
    SECTOR_MAPPING_PATH,
    REPORTS_DIR,
    TOP_N_RECOMMENDATIONS,
)
from src.analysis.engine import score_fund
from src.analysis.ranking import rank_funds
from src.analysis.redemption import check_redemption_signals, RedemptionSignal
from src.data.fund_holdings import fetch_fund_holdings
from src.data.fund_manager import fetch_fund_manager, fetch_fund_ranking
from src.data.fund_nav import fetch_fund_nav, fetch_current_nav
from src.data.market_data import fetch_market_data
from src.data.news_data import fetch_market_sentiment, fetch_sector_news, fetch_fund_news
from src.output.dingtalk import DingTalkSender
from src.output.formatter import (
    format_recommendation_report,
    format_redemption_alert,
    format_held_funds_tracking,
)
from src.state.tracker import PortfolioTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("fund_analysis")


def load_watchlist() -> dict:
    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sector_mapping() -> dict[str, list[str]]:
    with open(SECTOR_MAPPING_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("sector_to_boards", {})


def run_weekly():
    """Full Monday analysis workflow."""
    logger.info("=== Starting Weekly Fund Analysis ===")

    watchlist = load_watchlist()
    sector_boards = load_sector_mapping()
    tracker = PortfolioTracker()
    dingtalk = DingTalkSender()

    # Phase 1: Fetch market data (once for all sectors)
    logger.info("Phase 1: Fetching market data...")
    market_snapshot = fetch_market_data(sector_boards)
    market_sentiment = fetch_market_sentiment() or 50.0

    # Phase 2: For each sector, for each fund, fetch data and score
    logger.info("Phase 2: Fetching fund data and scoring...")
    all_scores = []

    for sector in SECTOR_LIST:
        sector_funds = watchlist.get("sectors", {}).get(sector, [])
        if not sector_funds:
            logger.warning("No funds configured for sector: %s", sector)
            continue

        market_data = market_snapshot.sectors.get(sector)
        if market_data is None or market_data.error:
            logger.warning("Market data unavailable for %s, skipping", sector)
            continue

        sector_news = fetch_sector_news(sector, sector_boards.get(sector, [sector]))

        for fund_info in sector_funds:
            code = fund_info["code"]
            name = fund_info["name"]
            logger.info("Analyzing %s (%s) [%s]...", name, code, sector)

            # Fetch all fund data
            nav = fetch_fund_nav(code, name)
            holdings = fetch_fund_holdings(code, name, sector)
            manager = fetch_fund_manager(code, name)
            fund_news = fetch_fund_news(code, name)

            if nav.error:
                logger.warning("Skipping %s: NAV data error: %s", code, nav.error)
                continue

            # Score the fund
            score = score_fund(
                fund_code=code,
                fund_name=name,
                sector=sector,
                nav=nav,
                holdings=holdings,
                manager=manager,
                market=market_data,
                fund_news=fund_news,
                sector_news=sector_news,
                market_sentiment=market_sentiment,
            )
            all_scores.append(score)
            logger.info("  %s - Total: %.1f | Levels: %s", code, score.total_score, score.dimension_scores)

    if not all_scores:
        logger.error("No fund scores computed! Check data sources.")
        dingtalk.send_text("⚠️ 基金分析失败：所有基金数据获取失败，请检查数据源。")
        return

    # Phase 3: Rank and select top 5
    logger.info("Phase 3: Ranking funds...")
    recommendations = rank_funds(all_scores, TOP_N_RECOMMENDATIONS)

    logger.info("Top %d recommendations:", len(recommendations))
    for i, fs in enumerate(recommendations, 1):
        logger.info("  %d. %s (%s) - Score: %.1f - %s", i, fs.fund_name, fs.fund_code, fs.total_score, fs.recommendation_level)

    # Phase 4: Format and send report
    logger.info("Phase 4: Formatting and sending report...")
    report = format_recommendation_report(recommendations, market_snapshot)

    # Add held funds tracking section
    holdings = tracker.get_holdings()
    nav_cache = {}
    for h in holdings:
        code = h.get("fund_code", "")
        if code:
            nav_cache[code] = fetch_fund_nav(code, h.get("fund_name", ""))

    held_section = format_held_funds_tracking(holdings, nav_cache)
    full_report = report + "\n\n" + held_section

    # Save to file
    report_date = datetime.now().strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"{report_date}_weekly.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(full_report)
    logger.info("Report saved to %s", report_path)

    # Send to DingTalk
    title = f"基金周报 {report_date}"
    dingtalk.send_report(title, full_report)

    # Phase 5: Check held funds for redemption signals
    logger.info("Phase 5: Checking redemption signals...")
    for h in holdings:
        code = h["fund_code"]
        name = h.get("fund_name", code)
        purchase_nav = h.get("purchase_nav", 0)
        holding_days = tracker.get_holding_days(code)
        current_nav = fetch_current_nav(code)

        if current_nav is None:
            logger.warning("Cannot fetch current NAV for %s, skipping redemption check", code)
            continue

        nav_data = fetch_fund_nav(code, name)

        signals = check_redemption_signals(
            fund_code=code,
            fund_name=name,
            purchase_nav=purchase_nav,
            holding_days=holding_days,
            nav_data=nav_data,
            market_data=None,
            previous_rank_pct=None,
            current_rank_pct=None,
            sector_negative_news=False,
        )

        current_pnl = tracker.get_current_pnl(code, current_nav) or 0.0

        triggered = [s for s in signals if s.triggered]
        if triggered:
            alert_msg = format_redemption_alert(code, name, signals, current_pnl, holding_days)
            if alert_msg:
                logger.info("Redemption alert for %s: %d signals triggered", name, len(triggered))
                # Avoid duplicate alerts
                alert_key = f"redemption_{code}"
                if not tracker.has_alert_been_sent(code, alert_key):
                    dingtalk.send_markdown("🚨 赎回提醒", alert_msg)
                    tracker.record_alert(code, alert_key)

    tracker.save()
    logger.info("=== Weekly Analysis Complete ===")


def run_daily():
    """Daily redemption monitoring workflow."""
    logger.info("=== Starting Daily Redemption Monitor ===")

    tracker = PortfolioTracker()
    dingtalk = DingTalkSender()
    holdings = tracker.get_holdings()

    if not holdings:
        logger.info("No held funds, nothing to monitor.")
        return

    # Daily mode: skip heavy market data fetch, only check NAV + signals
    for h in holdings:
        code = h["fund_code"]
        name = h.get("fund_name", code)
        purchase_nav = h.get("purchase_nav", 0)
        holding_days = tracker.get_holding_days(code)
        sector = h.get("sector", "")

        logger.info("Monitoring %s (%s): day %d", name, code, holding_days)

        nav_data = fetch_fund_nav(code, name)
        market_data = market_snapshot.sectors.get(sector)
        current_nav = nav_data.current_nav if nav_data else None

        if current_nav is None:
            logger.warning("Cannot fetch NAV for %s", code)
            continue

        signals = check_redemption_signals(
            fund_code=code,
            fund_name=name,
            purchase_nav=purchase_nav,
            holding_days=holding_days,
            nav_data=nav_data,
            market_data=market_data,
            previous_rank_pct=None,
            current_rank_pct=None,
            sector_negative_news=False,
        )

        current_pnl = tracker.get_current_pnl(code, current_nav) or 0.0
        triggered = [s for s in signals if s.triggered]

        if triggered:
            alert_key = f"redemption_{code}_{datetime.now().strftime('%Y%m%d')}"
            if not tracker.has_alert_been_sent(code, alert_key):
                alert_msg = format_redemption_alert(code, name, signals, current_pnl, holding_days)
                if alert_msg:
                    dingtalk.send_markdown("🚨 赎回提醒", alert_msg)
                    tracker.record_alert(code, alert_key)
                    logger.info("Alert sent for %s", name)

    tracker.save()
    logger.info("=== Daily Monitor Complete ===")


def main():
    parser = argparse.ArgumentParser(description="Fund Analysis Agent")
    parser.add_argument(
        "--mode",
        choices=["weekly", "daily"],
        required=True,
        help="weekly: full analysis + recommendations; daily: redemption monitoring",
    )
    args = parser.parse_args()

    try:
        if args.mode == "weekly":
            run_weekly()
        else:
            run_daily()
    except Exception:
        logger.exception("Fatal error in %s mode", args.mode)
        # Try to notify via DingTalk
        try:
            DingTalkSender().send_text(
                f"⚠️ 基金分析Agent执行异常({args.mode})，请检查GitHub Actions日志。"
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
