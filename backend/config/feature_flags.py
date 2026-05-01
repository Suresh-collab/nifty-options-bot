"""
Feature-flag helper. Import and check flags like:
    from backend.config import feature_flags
    if feature_flags.is_enabled("ENABLE_ML_SIGNAL"): ...
"""
from backend.config.settings import get_settings

_FLAG_ATTRS = {
    "ENABLE_ML_SIGNAL": "enable_ml_signal",
    "ENABLE_LIVE_BROKER": "enable_live_broker",
    "ENABLE_AUTO_EXECUTION": "enable_auto_execution",
}


def is_enabled(flag: str) -> bool:
    attr = _FLAG_ATTRS.get(flag.upper())
    if attr is None:
        return False
    return bool(getattr(get_settings(), attr, False))


def all_flags() -> dict:
    s = get_settings()
    return {flag: bool(getattr(s, attr)) for flag, attr in _FLAG_ATTRS.items()}
