import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config
import db

SEED_SOURCE_PREFIX = "SEED_cam_"
SEED_LIKE = "SEED_%"
BASELINE_FPS = 100.0
BASELINE_BANDWIDTH_KB = 1024.0
DIP_FPS = 5.0
DIP_SLOT_START = {1: 900, 2: 2000}
DIP_SLOT_LENGTH = 20
GAP_SLOT_START = 2400
GAP_SLOT_LENGTH = 30
RESOLUTION = "1920x1080"


def source_names(cameras: int) -> list[str]:
    return [f"{SEED_SOURCE_PREFIX}{index:02d}" for index in range(1, cameras + 1)]


def sample_rows(sources: list[str], start: int, slots: int, sample_seconds: int) -> list[tuple]:
    rows = []
    for index, source in enumerate(sources):
        dip_start = DIP_SLOT_START.get(index)
        for slot in range(slots):
            if index == 0 and GAP_SLOT_START <= slot < GAP_SLOT_START + GAP_SLOT_LENGTH:
                continue
            dipping = dip_start is not None and dip_start <= slot < dip_start + DIP_SLOT_LENGTH
            rows.append(
                (source, start + slot * sample_seconds,
                 DIP_FPS if dipping else BASELINE_FPS, BASELINE_BANDWIDTH_KB)
            )
    return rows


def has_real_data(conn) -> bool:
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM {db.SAMPLES} WHERE source NOT LIKE ?", (SEED_LIKE,)
    ).fetchone()
    return int(row["n"]) > 0


def clear(conn) -> None:
    for table in (db.SAMPLES, db.CAMERAS, db.NOTIFICATIONS):
        conn.execute(f"DELETE FROM {table} WHERE source LIKE ?", (SEED_LIKE,))
    conn.execute(f"DELETE FROM {db.SETTINGS} WHERE key = 'seeded'")


def seed(conn, cameras: int, sample_seconds: int, retention_days: float, now: float) -> int:
    slots = int(retention_days * 86400 / sample_seconds)
    start = int(now) - slots * sample_seconds
    sources = source_names(cameras)

    conn.execute("BEGIN")
    rows = sample_rows(sources, start, slots, sample_seconds)
    db.add_samples(conn, rows)

    last_seen = start + (slots - 1) * sample_seconds
    for source in sources:
        db.save_camera(conn, source, RESOLUTION, 0.0, 0, last_seen)

    for index, dip_start in DIP_SLOT_START.items():
        if index >= len(sources):
            continue
        db.add_notification(
            conn, start + dip_start * sample_seconds, sources[index], RESOLUTION,
            DIP_FPS, BASELINE_BANDWIDTH_KB, 1, True, None,
        )

    db.set_setting(conn, "seeded", "1")
    conn.execute("COMMIT")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill the database with obviously fake data.")
    parser.add_argument("--cameras", type=int, default=32)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    path = args.db or config.DB_PATH
    db.init(path)
    conn = db.connect(path)
    try:
        if args.clear:
            clear(conn)
            print(f"cleared seed data from {path}")
            return 0
        if has_real_data(conn) and not args.force:
            print(f"refusing: {path} already holds non-seed samples (use --force)")
            return 1
        rows = seed(conn, args.cameras, config.SAMPLE_SECONDS,
                    config.RETENTION_DAYS, time.time())
        print(f"seeded {args.cameras} cameras, {rows} samples into {path}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
