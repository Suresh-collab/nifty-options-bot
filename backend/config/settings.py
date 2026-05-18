from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required — startup raises ValidationError with field name if missing
    database_url: str

    # Optional — falls back to pooler URL when not set
    database_migration_url: str = ""

    log_level: str = "INFO"

    # Feature flags — all OFF by default; real-money activation deferred to end
    enable_ml_signal: bool = False
    enable_live_broker: bool = False
    enable_auto_execution: bool = False

    # Leading-indicator additions (added after divergence + OI Buildup validation).
    # All OFF until the supporting work is verified per the recommendation flow:
    #   • DIVERGENCE_SIGNAL — gates wiring divergence into ai/signal_engine.py
    #   • DIVERGENCE_FEATURE — gates the rsi_divergence column in ml/features.py
    #                          (requires the model to be retrained on the extended set)
    #   • OI_FLOW_LOGGING — gates the background poller that snapshots option chains
    #                       into oi_snapshots so OI Buildup can be forward-tested
    enable_divergence_signal:  bool = False
    enable_divergence_feature: bool = False
    enable_oi_flow_logging:    bool = False
    # Tuned Combined Rule (walk-forward validated 2026-05-18 against NIFTY 15m):
    #   wST=0, wMACD=15, wRSI=30, rsi=25/60, thr=10. Wilson-95% LB ~58% on both
    #   train (125 trades) and test (66 trades). Affects backtesting/engine.py
    #   only — live signal_engine.py is intentionally untouched until paper-trade
    #   validation completes (>= 50 live trades, WR >= 50%).
    enable_tuned_rule:         bool = False
    # Snapshot interval in seconds for the OI poller (NSE chain refreshes ~60s).
    oi_snapshot_interval_sec:  float = 60.0

    # ML model version pin — empty string means "use latest active model".
    # Set to e.g. "v1" to roll back to a specific trained version without
    # touching the DB is_active flag.
    ml_model_version: str = ""

    # ── Phase 5 notification settings ────────────────────────────────────
    # Telegram — leave blank to disable
    telegram_bot_token: str = ""
    telegram_chat_id:   str = ""
    # SMTP email — leave blank to disable
    smtp_host:          str = ""
    smtp_port:          int = 587
    smtp_user:          str = ""
    smtp_password:      str = ""
    alert_email_to:     str = ""
    # Alert de-dup TTL in seconds (default 60 s per TDD 5.4)
    alert_dedup_ttl:    float = 60.0

    # ── Phase 4 broker settings ───────────────────────────────────────────
    # "paper" (default) or "live".  ENABLE_LIVE_BROKER must also be true for
    # live mode to activate — belt-and-suspenders guard.
    broker_mode: str = "paper"
    # Fernet key for encrypting Kite API credentials at rest.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    broker_encryption_key: str = ""
    # Per-install salt prepended to plaintext before Fernet encryption.
    broker_salt: str = ""

    # ── Real-time market data ─────────────────────────────────────────────
    # Twelve Data API key — free tier = 800 calls/day; leave blank to use
    # yfinance (15-min delayed). Get key at https://twelvedata.com
    twelvedata_api_key: str = ""

    # ── Phase 3 risk settings ─────────────────────────────────────────────
    # Reference capital for daily P&L limit calculations.
    paper_trading_capital: float = 100_000.0
    # Halt all trading when daily loss exceeds this fraction of capital.
    daily_loss_limit_pct: float = 0.02
    # Halt all trading when daily profit exceeds this fraction (lock-in target).
    daily_profit_target_pct: float = 0.05
    # Maximum number of simultaneously open paper trades (global cap).
    max_open_positions: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
