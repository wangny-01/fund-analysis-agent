import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

import akshare as ak

from src.data.fetcher import safe_fetch

logger = logging.getLogger(__name__)


@dataclass
class FundManagerData:
    fund_code: str
    fund_name: str
    manager_name: str = ""
    tenure_years: float = 0.0
    total_aum_yuan: float = 0.0
    funds_managed_count: int = 0
    historical_annual_return: Optional[float] = None
    recent_change: bool = False
    management_fee: float = 0.0
    error: Optional[str] = None


def fetch_fund_manager(fund_code: str, fund_name: str = "") -> FundManagerData:
    """Fetch fund manager profile and historical performance."""
    result = FundManagerData(fund_code=fund_code, fund_name=fund_name)

    try:
        # fund_manager_em() takes no params, returns all managers; filter by fund code
        df = safe_fetch(ak.fund_manager_em, cache_ttl_seconds=7200)

        if df is not None and not df.empty:
            df.columns = [str(c) for c in df.columns]

            # Find columns
            code_col = name_col = tenure_col = fund_count_col = return_col = None
            for c in df.columns:
                cl = c.lower()
                if "代码" in c or "code" in cl:
                    code_col = c
                if "姓名" in c:
                    name_col = c
                if "任职" in c or "年限" in c:
                    tenure_col = c
                if "基金" in c and ("管理" in c or "数量" in c or "只数" in c):
                    fund_count_col = c
                if "回报" in c or "收益" in c or "业绩" in c:
                    return_col = c

            # Try to find the row for this fund
            if code_col:
                mask = df[code_col].astype(str).str.strip() == fund_code.strip()
                if mask.any():
                    row = df[mask].iloc[0]
                else:
                    row = df.iloc[0]
            else:
                row = df.iloc[0]

            if name_col:
                result.manager_name = str(row[name_col]) if pd.notna(row[name_col]) else ""
            if tenure_col:
                raw = str(row[tenure_col]) if pd.notna(row[tenure_col]) else "0"
                try:
                    result.tenure_years = float(raw.replace("年", "").strip())
                except ValueError:
                    result.tenure_years = 0.0
            if fund_count_col:
                val = pd.to_numeric(row[fund_count_col], errors="coerce")
                result.funds_managed_count = int(val) if pd.notna(val) else 0
            if return_col:
                val = pd.to_numeric(row[return_col], errors="coerce")
                if pd.notna(val):
                    result.historical_annual_return = float(val)
        else:
            result.manager_name = "未知"

    except Exception as e:
        logger.error("fetch_fund_manager(%s): %s", fund_code, e)
        result.error = str(e)

    return result


def fetch_fund_ranking(fund_code: str) -> Optional[float]:
    """Fetch fund's percentile ranking within its category. Returns 0-1 where 0=top."""
    try:
        df = safe_fetch(
            ak.fund_open_fund_rank_em,
            symbol="全部",
            cache_ttl_seconds=1800,
        )

        if df is None or df.empty:
            return None

        df.columns = [str(c) for c in df.columns]

        code_col = rank_col = total_col = None
        for c in df.columns:
            cl = c.lower()
            if "代码" in c:
                code_col = c
            if "排名" in c:
                rank_col = c
            if "总数" in c or "total" in cl:
                total_col = c

        if code_col is None or rank_col is None:
            return None

        row = df[df[code_col].astype(str).str.strip() == fund_code.strip()]
        if row.empty:
            return None

        rank = pd.to_numeric(row.iloc[0][rank_col], errors="coerce")
        if pd.isna(rank):
            return None

        if total_col:
            total = pd.to_numeric(row.iloc[0][total_col], errors="coerce")
            if pd.notna(total) and total > 0:
                return float(rank / total)

        return float(rank / max(len(df), 1))

    except Exception as e:
        logger.error("fetch_fund_ranking(%s): %s", fund_code, e)
        return None
