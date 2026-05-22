import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from datetime import datetime
from typing import Optional

import requests

from config.settings import (
    DINGTALK_WEBHOOK_URL,
    DINGTALK_SECRET,
    DINGTALK_MAX_MSG_CHARS,
    DINGTALK_MSG_DELAY,
)

logger = logging.getLogger(__name__)


def _build_signed_url(webhook_url: str, secret: str) -> str:
    """Add timestamp and HMAC-SHA256 signature to DingTalk webhook URL."""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        key=secret.encode("utf-8"),
        msg=string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
    separator = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}&timestamp={timestamp}&sign={sign}"


class DingTalkSender:
    def __init__(self, webhook_url: str = "", secret: str = ""):
        self.webhook_url = webhook_url or DINGTALK_WEBHOOK_URL
        self.secret = secret or DINGTALK_SECRET

    def _get_signed_url(self) -> str:
        if self.secret:
            return _build_signed_url(self.webhook_url, self.secret)
        return self.webhook_url

    def send_markdown(self, title: str, text: str) -> bool:
        if not self.webhook_url:
            logger.warning("DingTalk webhook URL not configured, skipping send.")
            return False

        url = self._get_signed_url()
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title[:128],
                "text": text,
            },
        }

        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=15,
                headers={"Content-Type": "application/json"},
            )
            data = resp.json()
            if data.get("errcode") == 0:
                logger.info("DingTalk message sent: %s", title)
                return True
            else:
                logger.error("DingTalk error: %s", data.get("errmsg", "unknown"))
                return False
        except Exception as e:
            logger.error("DingTalk send failed: %s", e)
            return False

    def send_text(self, content: str) -> bool:
        if not self.webhook_url:
            logger.warning("DingTalk webhook URL not configured, skipping send.")
            return False

        url = self._get_signed_url()
        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            return data.get("errcode") == 0
        except Exception as e:
            logger.error("DingTalk text send failed: %s", e)
            return False

    def send_report(self, title: str, report: str) -> bool:
        if not self.webhook_url:
            logger.warning("DingTalk webhook URL not configured, skipping send.")
            return False

        if len(report) <= DINGTALK_MAX_MSG_CHARS:
            return self.send_markdown(title, report)

        sections = []
        current = ""
        for line in report.split("\n"):
            if line.startswith("## ") and current and len(current) > 200:
                sections.append(current.strip())
                current = line + "\n"
            else:
                current += line + "\n"

        if current.strip():
            sections.append(current.strip())

        messages = []
        buffer = ""
        for section in sections:
            if len(buffer) + len(section) < DINGTALK_MAX_MSG_CHARS:
                buffer += "\n\n" + section if buffer else section
            else:
                if buffer:
                    messages.append(buffer)
                buffer = section
        if buffer:
            messages.append(buffer)

        success_count = 0
        for i, msg in enumerate(messages):
            part_title = f"{title} ({i + 1}/{len(messages)})"
            if self.send_markdown(part_title, msg):
                success_count += 1
                if i < len(messages) - 1:
                    time.sleep(DINGTALK_MSG_DELAY)

        logger.info("Sent %d/%d DingTalk message parts", success_count, len(messages))
        return success_count == len(messages)
