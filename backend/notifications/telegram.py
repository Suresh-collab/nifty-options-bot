"""
Phase 5.2 — Telegram bot alerts.

Sends messages via the Telegram Bot API (HTTPS POST — no extra library needed,
just httpx which is already in requirements).

Required env vars (in config/settings.py):
    TELEGRAM_BOT_TOKEN  — from @BotFather
    TELEGRAM_CHAT_ID    — target chat / channel ID (negative for channels)

If either var is empty the module silently no-ops (safe to call at startup
before the user has configured Telegram).

Alert types sent automatically:
    - trade_entry      : BUY_CE / BUY_PE executed
    - trade_exit       : position closed, P&L reported
    - sl_hit           : stop-loss triggered
    - daily_cutoff     : daily loss/profit limit reached
    - kill_switch      : kill switch activated
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from notifications.dedup import should_send

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


async def send_message(
    text: str,
    *,
    bot_token: str,
    chat_id: str,
    parse_mode: str = "HTML",
    dedup_key: Optional[str] = None,
) -> bool:
    """
    Send a plain or HTML-formatted message to a Telegram chat.
    Returns True if delivered, False if skipped (dedup) or failed (error logged).
    """
    if not bot_token or not chat_id:
        return False

    if dedup_key and not should_send(dedup_key):
        logger.debug("Telegram alert suppressed by dedup: %s", dedup_key)
        return False

    url = _TELEGRAM_API.format(token=bot_token)
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        logger.info("Telegram alert sent (dedup_key=%s)", dedup_key)
        return True
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False


async def send_trade_alert(
    event: str,
    ticker: str,
    direction: str,
    strike: float,
    price: float,
    pnl: Optional[float] = None,
    *,
    bot_token: str,
    chat_id: str,
) -> bool:
    """
    Structured trade alert.  Required fields (TDD 5.2):
        event, ticker, direction, strike, price
    Optional: pnl (for exit / SL alerts).
    """
    event_emoji = {
        "trade_entry":   "🟢",
        "trade_exit":    "🔵",
        "sl_hit":        "🔴",
        "daily_cutoff":  "🛑",
        "kill_switch":   "⚠️",
    }.get(event, "ℹ️")

    lines = [
        f"{event_emoji} <b>{event.upper().replace('_', ' ')}</b>",
        f"Ticker:    {ticker}",
        f"Direction: {direction}",
        f"Strike:    {strike}",
        f"Price:     ₹{price:.2f}",
    ]
    if pnl is not None:
        lines.append(f"P&amp;L:      ₹{pnl:+.2f}")

    text = "\n".join(lines)
    dedup_key = f"tg:{event}:{ticker}:{direction}:{strike}"
    return await send_message(
        text, bot_token=bot_token, chat_id=chat_id, dedup_key=dedup_key
    )
