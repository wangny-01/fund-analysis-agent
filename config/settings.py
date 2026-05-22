import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PORTFOLIO_STATE_PATH = DATA_DIR / "portfolio_state.json"
OUTPUT_DIR = PROJECT_ROOT / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
CONFIG_DIR = PROJECT_ROOT / "config"
WATCHLIST_PATH = CONFIG_DIR / "fund_watchlist.yaml"
SECTOR_MAPPING_PATH = CONFIG_DIR / "sector_mapping.yaml"

DINGTALK_WEBHOOK_URL = os.environ.get("DINGTALK_WEBHOOK_URL", "")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET", "")
DINGTALK_MAX_MSG_CHARS = 3500
DINGTALK_MSG_DELAY = 3.0

SECTOR_LIST = ["科技", "消费", "医疗", "新能源", "军工", "金融", "房地产", "有色金属"]
TOP_N_RECOMMENDATIONS = 5
DEFAULT_HOLD_DAYS = 7
MAX_HOLD_DAYS = 9

DIMENSION_WEIGHTS = {
    "nav_performance": 0.25,
    "holdings_quality": 0.15,
    "risk_metrics": 0.20,
    "market_policy": 0.15,
    "news_sentiment": 0.10,
    "manager_quality": 0.15,
}

GREEN_THRESHOLD = 7.5
YELLOW_THRESHOLD = 5.0

RISK_FREE_RATE = 0.025
TRADING_DAYS_PER_YEAR = 244
TRADING_DAYS_1W = 5
TRADING_DAYS_1M = 22
TRADING_DAYS_3M = 66

MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0
CACHE_TTL_SECONDS = 300

CHECK_TRADING_DAY = True
