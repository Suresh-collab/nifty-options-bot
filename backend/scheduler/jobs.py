"""
Phase 6 — APScheduler jobs wired into FastAPI lifespan.

Jobs:
  daily_summary  — sends email P&L summary at 3:30 PM IST (10:00 UTC) every weekday
"""
import logging

logger = logging.getLogger(__name__)


async def daily_summary_job() -> None:
    """Send today's paper-trade P&L summary via email."""
    try:
        from datetime import datetime
        from paper_trading.simulator import get_history, get_stats
        from notifications.email import send_daily_summary
        from config.settings import get_settings

        cfg = get_settings()
        if not cfg.alert_email_to:
            logger.debug("daily_summary_job: ALERT_EMAIL_TO not set, skipping")
            return

        trades     = get_history()
        stats      = get_stats()
        today      = datetime.now().strftime("%Y-%m-%d")
        today_trades = [t for t in trades if t.get("exit_time", "").startswith(today)]

        await send_daily_summary(
            trades=today_trades,
            total_pnl=stats.get("total_pnl", 0),
            smtp_host=cfg.smtp_host,
            smtp_port=cfg.smtp_port,
            smtp_user=cfg.smtp_user,
            smtp_password=cfg.smtp_password,
            to_address=cfg.alert_email_to,
        )
        logger.info("daily_summary sent: %d trades, PNL=%.2f", len(today_trades), stats.get("total_pnl", 0))
    except Exception as exc:
        logger.warning("daily_summary_job failed: %s", exc)


def create_scheduler():
    """Build a configured AsyncIOScheduler. Call .start() in lifespan."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler(timezone="UTC")
    # 3:30 PM IST = 10:00 UTC; mon-fri only
    scheduler.add_job(
        daily_summary_job,
        CronTrigger(day_of_week="mon-fri", hour=10, minute=0, timezone="UTC"),
        id="daily_summary",
        replace_existing=True,
    )
    return scheduler
