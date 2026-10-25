import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
STATIC_DIR = SCRIPT_DIR / "static"
APEXCHARTS_DIR = SCRIPT_DIR.parent / "apexcharts-js"

DB_PATH = Path(os.environ.get("DB_PATH", SCRIPT_DIR / "zoneminder_monitoring.db"))
SAMPLE_SECONDS = int(os.environ.get("SAMPLE_SECONDS", "60"))
RETENTION_DAYS = float(os.environ.get("RETENTION_DAYS", "2"))
LOW_FPS_THRESHOLD = float(os.environ.get("LOW_FPS_THRESHOLD", "18"))
DISPLAY_TZ = os.environ.get("DISPLAY_TZ", "Asia/Ho_Chi_Minh")
PAUSE_PASSPHRASE = os.environ.get("PAUSE_PASSPHRASE", "")

BACKOFF_H = [1, 2, 4, 8, 24]
MIN_SAMPLES = 3
MAX_SAMPLES = 3

DB_SIZE_SAMPLE_INTERVAL_S = 3600
DB_SIZE_SAMPLE_COUNT = 24 * 7

SECONDS_PER_DAY = 86400


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing env var: {name}")
    return value


def flag(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in {"1", "true", "yes"}


def tz() -> ZoneInfo:
    return ZoneInfo(DISPLAY_TZ)
