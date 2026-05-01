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


@lru_cache
def get_settings() -> Settings:
    return Settings()
