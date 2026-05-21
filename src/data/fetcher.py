import functools
import hashlib
import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[datetime, Any]] = {}


def _cache_key(func: Callable, *args, **kwargs) -> str:
    raw = json.dumps(
        {"name": func.__name__, "args": args, "kwargs": kwargs},
        sort_keys=True,
        default=str,
    )
    return hashlib.md5(raw.encode()).hexdigest()


def safe_fetch(
    func: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 2.0,
    cache_ttl_seconds: int = 300,
    **kwargs,
) -> Optional[Any]:
    """
    Wraps any akshare function with retry, jitter, caching, and graceful degradation.

    Returns None on total failure, otherwise the function result (typically DataFrame).
    """
    key = _cache_key(func, *args, **kwargs)
    if key in _cache:
        ts, val = _cache[key]
        if datetime.now() - ts < timedelta(seconds=cache_ttl_seconds):
            logger.debug("Cache hit for %s (age=%s)", func.__name__, datetime.now() - ts)
            return val

    last_error = None
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                jitter = random.uniform(0.5, 1.5)
                sleep_time = base_delay * (2 ** (attempt - 1)) + jitter
                logger.debug("Retry %d/%d for %s, sleeping %.1fs", attempt + 1, max_retries, func.__name__, sleep_time)
                time.sleep(sleep_time)
            else:
                time.sleep(random.uniform(0.3, 1.0))

            result = func(*args, **kwargs)

            if result is not None:
                if isinstance(result, pd.DataFrame) and result.empty:
                    logger.warning("%s returned empty DataFrame (attempt %d)", func.__name__, attempt + 1)
                    continue
                _cache[key] = (datetime.now(), result)
                return result
        except Exception as e:
            last_error = e
            logger.warning("Attempt %d/%d for %s failed: %s", attempt + 1, max_retries, func.__name__, e)

    logger.error("All %d attempts for %s failed. Last error: %s", max_retries, func.__name__, last_error)
    return None


def clear_cache():
    """Clear the in-memory fetch cache."""
    _cache.clear()


def cached(func: Callable) -> Callable:
    """Decorator: wrap a function with safe_fetch defaults."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return safe_fetch(func, *args, **kwargs)

    return wrapper
