#!/usr/bin/env python3
import configparser
import os


# ---------- helpers ----------
def env(name, default=None, cast=str):
    v = os.getenv(name, None if default is None else str(default))
    if v is None:
        return default
    if cast is int:
        return int(v)
    if cast is float:
        return float(v)
    if cast is bool:
        return str(v).lower() in ("1", "true", "yes", "on")
    return v


_cfg = None


def ini(path=None):
    """Load config.ini with ExtendedInterpolation once."""
    global _cfg
    if _cfg is not None:
        return _cfg
    cp = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    default_path = os.path.join(os.path.dirname(__file__), "..", "config.ini")
    cp.read(path or default_path)
    _cfg = cp
    return _cfg


def cfg_get(section, key, default=None, cast=str):
    cp = ini()
    try:
        v = cp.get(section, key, fallback=None)
    except Exception:
        v = None
    if v is None:
        return default
    if cast is int:
        return int(v)
    if cast is float:
        return float(v)
    if cast is bool:
        return str(v).lower() in ("1", "true", "yes", "on")
    return v


# ---------- paths ----------
DB_PATH = env("VC_DB", cfg_get("paths", "db_path", "data/eplus_vc.sqlite3"))
LOG_DIR = env("VC_LOG_DIR", cfg_get("paths", "log_dir", "logs"))

# ---------- resolver / slate / placeholders ----------
RESOLVER_BASE = env(
    "VC_RESOLVER_ORIGIN", cfg_get("resolver", "base", "http://127.0.0.1:8094")
)
SLATE_URL = env("VC_SLATE_URL", cfg_get("resolver", "slate_url", ""))
PLACEHOLDER_TITLE = env(
    "VC_PLACEHOLDER_TITLE", cfg_get("placeholders", "title", "Stand By")
)
PLACEHOLDER_SUBTITLE = env(
    "VC_PLACEHOLDER_SUBTITLE", cfg_get("placeholders", "subtitle", "")
)
PLACEHOLDER_SUMMARY = env(
    "VC_PLACEHOLDER_SUMMARY",
    cfg_get("placeholders", "summary", "No live event scheduled"),
)

# ---------- watch graph ----------
WATCH_API_BASE = env(
    "WATCH_API_BASE",
    cfg_get("watch", "api_base", "https://watch.graph.api.espn.com/api"),
)
WATCH_API_KEY = env(
    "WATCH_API_KEY", cfg_get("watch", "api_key", "0dbf88e8-cc6d-41da-aa83-18b5c630bc5c")
)
WATCH_FEATURES = env("WATCH_FEATURES", cfg_get("watch", "features", "pbov7"))
WATCH_DEFAULT_REGION = env("WATCH_API_REGION", cfg_get("watch", "region", "US"))
WATCH_DEFAULT_TZ = env("WATCH_API_TZ", cfg_get("watch", "tz", "America/New_York"))
WATCH_DEFAULT_DEVICE = env("WATCH_API_DEVICE", cfg_get("watch", "device", "desktop"))
WATCH_VERIFY_SSL = env(
    "WATCH_API_VERIFY_SSL", cfg_get("watch", "verify_ssl", "1"), cast=bool
)
