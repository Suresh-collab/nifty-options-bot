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
