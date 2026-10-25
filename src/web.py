import secrets
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
import db

db_size_samples: deque[tuple[int, int]] = deque(maxlen=config.DB_SIZE_SAMPLE_COUNT)
db_size_window_s = config.DB_SIZE_SAMPLE_COUNT * config.DB_SIZE_SAMPLE_INTERVAL_S


def db_size_trend(samples, now, window_s=config.SECONDS_PER_DAY,
                  retention_s=db_size_window_s):
    fresh = [sample for sample in samples if now - sample[0] <= retention_s]
    if not fresh:
        return {"bytes": None, "delta": None}
    current = fresh[-1][1]
    if len(fresh) < 2:
        return {"bytes": current, "delta": None}
    cutoff = now - window_s
    older = [sample for sample in fresh if sample[0] <= cutoff]
    baseline = older[-1][1] if older else fresh[0][1]
    return {"bytes": current, "delta": current - baseline}


def check_passphrase(given: str | None, expected: str | None) -> bool:
    if not given or not expected:
        return False
    return secrets.compare_digest(given, expected)


def build_series_payload(rows, threshold: float, tz_name: str) -> dict:
    cameras: dict[str, dict] = {}
    for row in rows:
        camera = cameras.setdefault(
            row["source"],
            {"source": row["source"], "resolution": row["resolution"], "points": []},
        )
        camera["points"].append([
            int(row["ts"]),
            round(float(row["fps"]), 2),
            round(float(row["bandwidth_kb"]), 1),
        ])
    return {
        "threshold": threshold,
        "tz": tz_name,
        "cameras": [cameras[key] for key in sorted(cameras)],
    }


def build_status_payload(conn, now: float, size_samples=None) -> dict:
    newest = db.newest_ts(conn)
    last = db.latest_notification(conn)
    samples = db_size_samples if size_samples is None else size_samples
    reporting_since = int(now) - 2 * config.SAMPLE_SECONDS
    return {
        "as_of": int(now),
        "collector_alive": newest is not None and now - newest <= 2 * config.SAMPLE_SECONDS,
        "stale_seconds": None if newest is None else int(now - newest),
        "cameras_reporting": db.cameras_reporting(conn, reporting_since),
        "cameras_known": db.camera_count(conn),
        "notify_enabled": db.notify_enabled(conn),
        "seeded": db.is_seeded(conn),
        "threshold": config.LOW_FPS_THRESHOLD,
        "tz": config.DISPLAY_TZ,
        "database": db_size_trend(samples, now),
        "last_email": None if last is None else {
            "ts": int(last["ts"]),
            "source": last["source"],
            "email_ok": bool(last["email_ok"]),
            "error": last["error"],
        },
    }


def build_full_payload(conn, now: float) -> dict:
    since = int(now - config.RETENTION_DAYS * config.SECONDS_PER_DAY)
    return {
        "as_of": int(now),
        "status": build_status_payload(conn, now),
        "cameras": [dict(row) for row in db.camera_overview(conn)],
        "series": build_series_payload(
            db.series(conn, since), config.LOW_FPS_THRESHOLD, config.DISPLAY_TZ
        ),
        "notifications": [dict(row) for row in db.notifications(conn, since)],
    }


class ControlRequest(BaseModel):
    passphrase: str
    enable: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


app = FastAPI(title="ZoneMinder monitoring", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return "<h1>ZoneMinder monitoring</h1><p>Dashboard arrives in Phase 2.4.</p>"


@app.get("/api/data")
def data(only: str | None = None):
    now = time.time()
    conn = db.connect()
    try:
        conn.execute("BEGIN")
        if only == "status":
            status = build_status_payload(conn, now)
            payload = {"as_of": status["as_of"], "status": status}
        else:
            payload = build_full_payload(conn, now)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return payload


@app.post("/api/control")
def control(request: ControlRequest) -> dict:
    if not check_passphrase(request.passphrase, config.PAUSE_PASSPHRASE):
        raise HTTPException(status_code=401, detail="invalid passphrase")
    conn = db.connect()
    try:
        db.set_setting(conn, "notify_enabled", "1" if request.enable else "0")
        enabled = db.notify_enabled(conn)
    finally:
        conn.close()
    return {"notify_enabled": enabled}
