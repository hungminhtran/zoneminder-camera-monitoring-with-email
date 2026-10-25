import sqlite3
from pathlib import Path

import config

PREFIX = "zoneminder_monitoring_"

SAMPLES = f"{PREFIX}samples"
CAMERAS = f"{PREFIX}cameras"
NOTIFICATIONS = f"{PREFIX}notifications"
SETTINGS = f"{PREFIX}settings"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {SAMPLES} (
    source       TEXT    NOT NULL,
    ts           INTEGER NOT NULL,
    fps          REAL    NOT NULL,
    bandwidth_kb REAL    NOT NULL,
    PRIMARY KEY (source, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS {CAMERAS} (
    source     TEXT PRIMARY KEY,
    resolution TEXT,
    next_at    REAL    NOT NULL DEFAULT 0,
    step       INTEGER NOT NULL DEFAULT 0,
    last_seen  INTEGER
);

CREATE TABLE IF NOT EXISTS {NOTIFICATIONS} (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           INTEGER NOT NULL,
    source       TEXT    NOT NULL,
    resolution   TEXT,
    avg_fps      REAL    NOT NULL,
    bandwidth_kb REAL,
    step         INTEGER NOT NULL,
    email_ok     INTEGER NOT NULL,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS {SETTINGS} (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

SAMPLE_UPSERT = f"""
INSERT INTO {SAMPLES} (source, ts, fps, bandwidth_kb) VALUES (?, ?, ?, ?)
ON CONFLICT(source, ts) DO UPDATE SET
    fps = excluded.fps,
    bandwidth_kb = excluded.bandwidth_kb
"""

CAMERA_UPSERT = f"""
INSERT INTO {CAMERAS} (source, resolution, next_at, step, last_seen)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(source) DO UPDATE SET
    resolution = excluded.resolution,
    next_at = excluded.next_at,
    step = excluded.step,
    last_seen = excluded.last_seen
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_size_limit=1048576")
    return conn


def init(path: Path | None = None) -> None:
    target = Path(path or config.DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(target)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def add_sample(conn: sqlite3.Connection, source: str, ts: int, fps: float,
               bandwidth_kb: float) -> None:
    conn.execute(SAMPLE_UPSERT, (source, ts, fps, bandwidth_kb))


def add_samples(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(SAMPLE_UPSERT, rows)


def recent_fps(conn: sqlite3.Connection, source: str, limit: int) -> list[float]:
    rows = conn.execute(
        f"SELECT fps FROM {SAMPLES} WHERE source = ? ORDER BY ts DESC LIMIT ?",
        (source, limit),
    ).fetchall()
    return [float(row["fps"]) for row in reversed(rows)]


def get_camera(conn: sqlite3.Connection, source: str) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT * FROM {CAMERAS} WHERE source = ?", (source,)
    ).fetchone()


def save_camera(conn: sqlite3.Connection, source: str, resolution: str | None,
                next_at: float, step: int, last_seen: int | None) -> None:
    conn.execute(CAMERA_UPSERT, (source, resolution, next_at, step, last_seen))


def add_notification(conn: sqlite3.Connection, ts: int, source: str,
                     resolution: str | None, avg_fps: float, bandwidth_kb: float | None,
                     step: int, email_ok: bool, error: str | None) -> None:
    conn.execute(
        f"""
        INSERT INTO {NOTIFICATIONS}
            (ts, source, resolution, avg_fps, bandwidth_kb, step, email_ok, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, source, resolution, avg_fps, bandwidth_kb, step, int(email_ok), error),
    )


def prune(conn: sqlite3.Connection, before: int) -> None:
    sources = conn.execute(f"SELECT source FROM {CAMERAS}").fetchall()
    for row in sources:
        conn.execute(
            f"DELETE FROM {SAMPLES} WHERE source = ? AND ts < ?",
            (row["source"], before),
        )
    conn.execute(f"DELETE FROM {NOTIFICATIONS} WHERE ts < ?", (before,))


def series(conn: sqlite3.Connection, since: int) -> list[sqlite3.Row]:
    return conn.execute(
        f"""
        SELECT s.source, c.resolution, s.ts, s.fps, s.bandwidth_kb
        FROM {SAMPLES} s
        LEFT JOIN {CAMERAS} c ON c.source = s.source
        WHERE s.ts >= ?
        ORDER BY s.source, s.ts
        """,
        (since,),
    ).fetchall()


def notifications(conn: sqlite3.Connection, since: int) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT * FROM {NOTIFICATIONS} WHERE ts >= ? ORDER BY ts DESC, id DESC",
        (since,),
    ).fetchall()


def camera_overview(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        f"""
        SELECT c.source, c.resolution, s.fps, s.bandwidth_kb, s.ts
        FROM {CAMERAS} c
        LEFT JOIN {SAMPLES} s
            ON s.source = c.source
           AND s.ts = (SELECT MAX(ts) FROM {SAMPLES} WHERE source = c.source)
        ORDER BY c.source
        """
    ).fetchall()


def newest_ts(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(f"SELECT MAX(ts) AS newest FROM {SAMPLES}").fetchone()
    return None if row["newest"] is None else int(row["newest"])


def camera_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS n FROM {CAMERAS}").fetchone()["n"])


def cameras_reporting(conn: sqlite3.Connection, since: int) -> int:
    return int(
        conn.execute(
            f"SELECT COUNT(DISTINCT source) AS n FROM {SAMPLES} WHERE ts >= ?", (since,)
        ).fetchone()["n"]
    )


def latest_notification(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT * FROM {NOTIFICATIONS} ORDER BY ts DESC, id DESC LIMIT 1"
    ).fetchone()


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute(f"SELECT value FROM {SETTINGS} WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        f"""
        INSERT INTO {SETTINGS} (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )


def notify_enabled(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, "notify_enabled", "1") != "0"


def is_seeded(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, "seeded", "0") == "1"


def file_size(path: Path) -> int:
    total = 0
    for suffix in ("", "-wal"):
        candidate = Path(f"{path}{suffix}")
        if candidate.exists():
            total += candidate.stat().st_size
    return total
