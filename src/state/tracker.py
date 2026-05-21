import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from config.settings import PORTFOLIO_STATE_PATH

logger = logging.getLogger(__name__)

DEFAULT_STATE = {
    "version": 1,
    "last_updated": "",
    "holdings": [],
    "history": [],
}


class PortfolioTracker:
    def __init__(self, state_path: Optional[Path] = None):
        self.state_path = state_path or PORTFOLIO_STATE_PATH
        self.state = self._load()

    def _load(self) -> dict:
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to load portfolio state: %s", e)
        return dict(DEFAULT_STATE)

    def save(self):
        self.state["last_updated"] = datetime.now().isoformat()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def get_holdings(self) -> list[dict]:
        return self.state.get("holdings", [])

    def buy(
        self,
        fund_code: str,
        fund_name: str,
        sector: str,
        nav: float,
        score: float,
        hold_days: int,
    ):
        """Record a new fund purchase."""
        today = date.today().isoformat()
        target_exit = (date.today() + timedelta(days=hold_days)).isoformat()

        holding = {
            "fund_code": fund_code,
            "fund_name": fund_name,
            "sector": sector,
            "purchase_date": today,
            "purchase_nav": nav,
            "purchase_score": score,
            "recommended_hold_days": hold_days,
            "target_exit_date": target_exit,
            "status": "holding",
            "alerts_sent": [],
        }

        self.state.setdefault("holdings", []).append(holding)
        self.save()
        logger.info("Bought %s (%s) at NAV %.4f", fund_name, fund_code, nav)

    def sell(self, fund_code: str, exit_nav: float, reason: str):
        """Mark a fund as sold, move to history."""
        holdings = self.state.get("holdings", [])
        for i, h in enumerate(holdings):
            if h["fund_code"] == fund_code and h["status"] == "holding":
                entry = holdings.pop(i)
                purchase_nav = entry["purchase_nav"]
                pnl_pct = (exit_nav / purchase_nav - 1) * 100 if purchase_nav > 0 else 0.0

                history_entry = {
                    "fund_code": entry["fund_code"],
                    "fund_name": entry["fund_name"],
                    "purchase_date": entry["purchase_date"],
                    "exit_date": date.today().isoformat(),
                    "purchase_nav": purchase_nav,
                    "exit_nav": exit_nav,
                    "pnl_pct": round(pnl_pct, 2),
                    "exit_reason": reason,
                }
                self.state.setdefault("history", []).append(history_entry)
                self.save()
                logger.info("Sold %s at NAV %.4f (P&L: %.2f%%)", fund_code, exit_nav, pnl_pct)
                return

        logger.warning("Fund %s not found in holdings", fund_code)

    def get_holding_days(self, fund_code: str) -> int:
        for h in self.state.get("holdings", []):
            if h["fund_code"] == fund_code and h["status"] == "holding":
                purchase_date = date.fromisoformat(h["purchase_date"])
                return (date.today() - purchase_date).days
        return 0

    def get_current_pnl(self, fund_code: str, current_nav: float) -> Optional[float]:
        for h in self.state.get("holdings", []):
            if h["fund_code"] == fund_code and h["status"] == "holding":
                purchase_nav = h.get("purchase_nav", 0.0)
                if purchase_nav > 0:
                    return (current_nav / purchase_nav - 1) * 100
        return None

    def record_alert(self, fund_code: str, alert_type: str):
        for h in self.state.get("holdings", []):
            if h["fund_code"] == fund_code:
                h.setdefault("alerts_sent", []).append({
                    "date": datetime.now().isoformat(),
                    "type": alert_type,
                })
                self.save()
                break

    def has_alert_been_sent(self, fund_code: str, alert_type: str) -> bool:
        """Check if same alert was already sent today."""
        today_str = date.today().isoformat()
        for h in self.state.get("holdings", []):
            if h["fund_code"] == fund_code:
                for alert in h.get("alerts_sent", []):
                    if alert_type in alert.get("type", "") and today_str in alert.get("date", ""):
                        return True
        return False
