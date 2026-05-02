"""
Phase 5.3 — Email alerts (daily summary + critical events).

Uses aiosmtplib for async SMTP delivery.

Required env vars (in config/settings.py):
    SMTP_HOST       — e.g. smtp.gmail.com
    SMTP_PORT       — e.g. 587
    SMTP_USER       — sender address
    SMTP_PASSWORD   — app password
    ALERT_EMAIL_TO  — recipient address

If any required var is empty the module silently no-ops.
"""
from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from notifications.dedup import should_send

logger = logging.getLogger(__name__)


async def send_email(
    subject: str,
    body_html: str,
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_address: str,
    dedup_key: Optional[str] = None,
) -> bool:
    """
    Send an HTML email via SMTP (STARTTLS).
    Returns True if delivered, False if skipped (dedup/config) or failed.
    """
    if not all([smtp_host, smtp_user, smtp_password, to_address]):
        return False

    if dedup_key and not should_send(dedup_key):
        logger.debug("Email suppressed by dedup: %s", dedup_key)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = to_address
    msg.attach(MIMEText(body_html, "html"))

    try:
        import aiosmtplib  # noqa: PLC0415 — optional dep, imported lazily
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            start_tls=True,
        )
        logger.info("Email sent: %s → %s", subject, to_address)
        return True
    except Exception as exc:
        logger.warning("Email send failed: %s", exc)
        return False


async def send_daily_summary(
    trades: list[dict],
    total_pnl: float,
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_address: str,
) -> bool:
    """
    Send the end-of-day P&L summary email (TDD 5.3).
    Builds an HTML table from closed trades and sends once per day (dedup TTL = 23h).
    """
    rows = "".join(
        f"<tr><td>{t.get('ticker','')}</td>"
        f"<td>{t.get('direction','')}</td>"
        f"<td>{t.get('entry_price','')}</td>"
        f"<td>{t.get('exit_price','')}</td>"
        f"<td style='color:{'green' if t.get('pnl',0)>=0 else 'red'}'>₹{t.get('pnl',0):+.2f}</td></tr>"
        for t in trades
    )
    body = f"""
    <h2>📊 Daily P&amp;L Summary</h2>
    <table border="1" cellpadding="4" cellspacing="0">
      <thead><tr><th>Ticker</th><th>Direction</th>
             <th>Entry</th><th>Exit</th><th>P&amp;L</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <p><strong>Total P&amp;L: ₹{total_pnl:+.2f}</strong></p>
    """
    from datetime import date
    dedup_key = f"email:daily_summary:{date.today().isoformat()}"
    return await send_email(
        subject=f"Daily P&L Summary — {date.today().isoformat()}",
        body_html=body,
        smtp_host=smtp_host, smtp_port=smtp_port,
        smtp_user=smtp_user, smtp_password=smtp_password,
        to_address=to_address,
        dedup_key=dedup_key,
    )


async def send_critical_alert(
    event: str,
    detail: str,
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_address: str,
) -> bool:
    """Send an immediate email for critical events (kill switch, daily cutoff)."""
    body = f"<h2>⚠️ {event}</h2><p>{detail}</p>"
    dedup_key = f"email:critical:{event}"
    return await send_email(
        subject=f"[ALERT] {event}",
        body_html=body,
        smtp_host=smtp_host, smtp_port=smtp_port,
        smtp_user=smtp_user, smtp_password=smtp_password,
        to_address=to_address,
        dedup_key=dedup_key,
    )
