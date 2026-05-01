"""0.3 — pydantic-settings config tests."""
import os
import pytest
from unittest.mock import patch


def test_settings_load_from_env(settings):
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.log_level in ("DEBUG", "INFO", "WARNING", "ERROR")


def test_feature_flags_default_off(settings):
    assert settings.enable_ml_signal is False
    assert settings.enable_live_broker is False
    assert settings.enable_auto_execution is False


def test_missing_database_url_raises():
    """Missing required var → startup raises with field name in message."""
    from pydantic import ValidationError
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class _StrictSettings(BaseSettings):
        model_config = SettingsConfigDict(env_file=None)  # no .env fallback
        database_url: str  # required

    env_without_url = {k: v for k, v in os.environ.items() if k.upper() != "DATABASE_URL"}
    with patch.dict(os.environ, env_without_url, clear=True):
        with pytest.raises(ValidationError, match="database_url"):
            _StrictSettings()
