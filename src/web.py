import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse

import config
import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


app = FastAPI(title="ZoneMinder monitoring", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)


def build_status(conn, now: float) -> dict:
    newest = db.newest_ts(conn)
    since = int(now) - 2 * config.SAMPLE_SECONDS
    last = db.latest_notification(conn)
    return {
        "as_of": int(now),
        "collector_alive": newest is not None and now - newest <= 2 * config.SAMPLE_SECONDS,
        "stale_seconds": None if newest is None else int(now - newest),
        "cameras_reporting": db.cameras_reporting(conn, since),
        "cameras_known": db.camera_count(conn),
        "notify_enabled": db.notify_enabled(conn),
        "seeded": db.is_seeded(conn),
        "database_bytes": db.file_size(config.DB_PATH),
        "last_email": None if last is None else {
            "ts": last["ts"],
            "source": last["source"],
            "email_ok": bool(last["email_ok"]),
            "error": last["error"],
        },
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return "<h1>ZoneMinder monitoring</h1><p>Dashboard arrives in Phase 2.</p>"


@app.get("/api/data")
def data(only: str | None = None):
    conn = db.connect()
    try:
        conn.execute("BEGIN")
        status = build_status(conn, time.time())
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    if only == "status":
        return {"as_of": status["as_of"], "status": status}
    return {
        "as_of": status["as_of"],
        "status": status,
        "cameras": [],
        "series": [],
        "notifications": [],
    }
