import math
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
STATIC_DIR = SCRIPT_DIR / "static"
APEXCHARTS_DIR = SCRIPT_DIR.parent / "apexcharts-js"

DEV = os.environ.get("DEV", "0").strip().lower() in {"1", "true", "yes"}
ENV_NAME = "dev" if DEV else "prod"

DB_DIR = Path(os.environ.get("DB_DIR", SCRIPT_DIR.parent))
DB_NAME = f"{ENV_NAME}_zoneminder_monitoring.db"
DB_PATH = Path(os.environ.get("DB_PATH", DB_DIR / DB_NAME))

SAMPLE_SECONDS = int(os.environ.get("SAMPLE_SECONDS", "60"))
RETENTION_DAYS = float(os.environ.get("RETENTION_DAYS", "2"))
LOW_FPS_THRESHOLD = float(os.environ.get("LOW_FPS_THRESHOLD", "3"))
DISPLAY_TZ = os.environ.get("DISPLAY_TZ", "Asia/Ho_Chi_Minh")
PAUSE_PASSPHRASE = os.environ.get("PAUSE_PASSPHRASE", "")

ALERT_WINDOW_S = int(os.environ.get("ALERT_WINDOW_S", "300"))
ALERT_WINDOW_SAMPLES = max(1, math.ceil(ALERT_WINDOW_S / SAMPLE_SECONDS))

BACKOFF_H = [1, 2, 4, 8, 24]

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
