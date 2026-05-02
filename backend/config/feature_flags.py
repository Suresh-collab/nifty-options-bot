"""
Feature-flag helper. Import and check flags like:
    from config import feature_flags
    if feature_flags.is_enabled("ENABLE_ML_SIGNAL"): ...

Phase 6 adds set_flag() for in-memory admin-UI overrides (resets on restart).
"""
from config.settings import get_settings

_FLAG_ATTRS = {
    "ENABLE_ML_SIGNAL": "enable_ml_signal",
    "ENABLE_LIVE_BROKER": "enable_live_broker",
    "ENABLE_AUTO_EXECUTION": "enable_auto_execution",
}

# In-memory overrides set via admin UI; take precedence over env/settings.
_overrides: dict = {}


def is_enabled(flag: str) -> bool:
    upper = flag.upper()
    if upper in _overrides:
        return _overrides[upper]
    attr = _FLAG_ATTRS.get(upper)
    if attr is None:
        return False
    return bool(getattr(get_settings(), attr, False))


def set_flag(flag: str, value: bool) -> None:
    """Override a flag in-memory (resets on server restart)."""
    upper = flag.upper()
    if upper not in _FLAG_ATTRS:
        raise ValueError(f"Unknown flag '{flag}'")
    _overrides[upper] = value


def all_flags() -> dict:
    return {flag: is_enabled(flag) for flag in _FLAG_ATTRS}
