import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent

DB_PATH = Path(os.environ.get("DB_PATH", SCRIPT_DIR / "zoneminder_monitoring.db"))
SAMPLE_SECONDS = int(os.environ.get("SAMPLE_SECONDS", "60"))
RETENTION_DAYS = float(os.environ.get("RETENTION_DAYS", "2"))
LOW_FPS_THRESHOLD = float(os.environ.get("LOW_FPS_THRESHOLD", "18"))
DISPLAY_TZ = os.environ.get("DISPLAY_TZ", "Asia/Ho_Chi_Minh")

BACKOFF_H = [1, 2, 4, 8, 24]
MIN_SAMPLES = 3
MAX_SAMPLES = 3

DB_SIZE_SAMPLE_INTERVAL_S = 3600
DB_SIZE_SAMPLE_COUNT = 24 * 7


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing env var: {name}")
    return value


def flag(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in {"1", "true", "yes"}


def tz() -> ZoneInfo:
    return ZoneInfo(DISPLAY_TZ)
