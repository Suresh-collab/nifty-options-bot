"""0.6 — feature-flag module tests."""
import os
import pytest
from unittest.mock import patch

from backend.config import feature_flags
from backend.config.settings import get_settings


def test_all_flags_default_off():
    flags = feature_flags.all_flags()
    assert flags["ENABLE_ML_SIGNAL"] is False
    assert flags["ENABLE_LIVE_BROKER"] is False
    assert flags["ENABLE_AUTO_EXECUTION"] is False


def test_unknown_flag_returns_false():
    assert feature_flags.is_enabled("NON_EXISTENT_FLAG") is False


def test_flag_enabled_via_env():
    """Flipping env var → is_enabled returns True (code path changes)."""
    get_settings.cache_clear()
    with patch.dict(os.environ, {"ENABLE_ML_SIGNAL": "true"}):
        get_settings.cache_clear()
        assert feature_flags.is_enabled("ENABLE_ML_SIGNAL") is True
    get_settings.cache_clear()


def test_flag_disabled_after_env_restored():
    get_settings.cache_clear()
    assert feature_flags.is_enabled("ENABLE_ML_SIGNAL") is False
