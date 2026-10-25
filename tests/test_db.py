import db


def row_count(conn, table):
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def test_tables_are_prefixed(conn):
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for table in (db.SAMPLES, db.CAMERAS, db.NOTIFICATIONS, db.SETTINGS):
        assert table in names
        assert table.startswith("zoneminder_monitoring_")


def test_add_sample_upserts_same_slot(conn):
    db.add_sample(conn, "cam_a", 1000, 20.0, 500.0)
    db.add_sample(conn, "cam_a", 1000, 12.5, 250.0)

    assert row_count(conn, db.SAMPLES) == 1
    stored = conn.execute(f"SELECT fps, bandwidth_kb FROM {db.SAMPLES}").fetchone()
    assert stored["fps"] == 12.5
    assert stored["bandwidth_kb"] == 250.0


def test_recent_fps_is_ascending_and_limited(conn):
    for slot in range(1, 6):
        db.add_sample(conn, "cam_a", slot, float(slot), 1.0)

    assert db.recent_fps(conn, "cam_a", 3) == [3.0, 4.0, 5.0]
    assert db.recent_fps(conn, "cam_a", 10) == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert db.recent_fps(conn, "missing", 3) == []


def test_save_camera_inserts_then_updates(conn):
    db.save_camera(conn, "cam_a", "1920x1080", 0.0, 0, 1000)
    db.save_camera(conn, "cam_a", "1280x720", 5000.0, 2, 2000)

    assert row_count(conn, db.CAMERAS) == 1
    camera = db.get_camera(conn, "cam_a")
    assert camera["resolution"] == "1280x720"
    assert camera["next_at"] == 5000.0
    assert camera["step"] == 2
    assert camera["last_seen"] == 2000


def test_get_camera_missing_returns_none(conn):
    assert db.get_camera(conn, "nope") is None


def test_backoff_state_survives_new_connection(conn, db_path):
    db.save_camera(conn, "cam_a", "1920x1080", 12345.0, 3, 1000)
    conn.close()

    reopened = db.connect(db_path)
    try:
        camera = db.get_camera(reopened, "cam_a")
        assert camera["next_at"] == 12345.0
        assert camera["step"] == 3
    finally:
        reopened.close()


def test_prune_keeps_cutoff_boundary(conn):
    db.save_camera(conn, "cam_a", "1920x1080", 0.0, 0, 200)
    for slot in (100, 199, 200, 201):
        db.add_sample(conn, "cam_a", slot, 20.0, 500.0)

    db.prune(conn, 200)

    remaining = [
        row["ts"] for row in conn.execute(f"SELECT ts FROM {db.SAMPLES} ORDER BY ts")
    ]
    assert remaining == [200, 201]


def test_prune_removes_old_notifications(conn):
    db.add_notification(conn, 100, "cam_a", "1920x1080", 5.0, 500.0, 1, True, None)
    db.add_notification(conn, 300, "cam_a", "1920x1080", 5.0, 500.0, 1, True, None)

    db.prune(conn, 200)

    assert row_count(conn, db.NOTIFICATIONS) == 1


def test_series_is_ordered_and_carries_resolution(conn):
    db.save_camera(conn, "cam_b", "1280x720", 0.0, 0, 30)
    db.save_camera(conn, "cam_a", "1920x1080", 0.0, 0, 30)
    db.add_sample(conn, "cam_b", 20, 21.0, 300.0)
    db.add_sample(conn, "cam_a", 30, 22.0, 400.0)
    db.add_sample(conn, "cam_a", 10, 18.0, 200.0)

    rows = db.series(conn, 0)

    assert [(row["source"], row["ts"]) for row in rows] == [
        ("cam_a", 10), ("cam_a", 30), ("cam_b", 20)
    ]
    assert rows[0]["resolution"] == "1920x1080"
    assert rows[2]["resolution"] == "1280x720"


def test_series_respects_since(conn):
    db.save_camera(conn, "cam_a", "1920x1080", 0.0, 0, 30)
    db.add_sample(conn, "cam_a", 10, 18.0, 200.0)
    db.add_sample(conn, "cam_a", 30, 22.0, 400.0)

    assert [row["ts"] for row in db.series(conn, 20)] == [30]


def test_camera_overview_returns_latest_sample_per_camera(conn):
    db.save_camera(conn, "cam_a", "1920x1080", 0.0, 0, 30)
    db.save_camera(conn, "cam_b", "1280x720", 0.0, 0, 30)
    db.save_camera(conn, "cam_c", "640x480", 0.0, 0, None)
    db.add_sample(conn, "cam_a", 10, 18.0, 200.0)
    db.add_sample(conn, "cam_a", 30, 22.5, 400.0)
    db.add_sample(conn, "cam_b", 30, 19.0, 300.0)

    overview = {row["source"]: row for row in db.camera_overview(conn)}

    assert overview["cam_a"]["ts"] == 30
    assert overview["cam_a"]["fps"] == 22.5
    assert overview["cam_b"]["fps"] == 19.0
    assert overview["cam_c"]["ts"] is None


def test_notifications_are_newest_first(conn):
    db.add_notification(conn, 100, "cam_a", "1920x1080", 5.0, 500.0, 1, True, None)
    db.add_notification(conn, 300, "cam_b", "1920x1080", 4.0, 400.0, 2, False, "smtp down")

    rows = db.notifications(conn, 0)

    assert [row["ts"] for row in rows] == [300, 100]
    assert rows[0]["email_ok"] == 0
    assert rows[0]["error"] == "smtp down"


def test_settings_round_trip_and_default(conn):
    assert db.get_setting(conn, "notify_enabled") is None
    assert db.get_setting(conn, "notify_enabled", "1") == "1"

    db.set_setting(conn, "notify_enabled", "0")
    db.set_setting(conn, "notify_enabled", "1")

    assert db.get_setting(conn, "notify_enabled") == "1"
    assert db.notify_enabled(conn) is True
    assert row_count(conn, db.SETTINGS) == 1


def test_notify_disabled_reads_false(conn):
    db.set_setting(conn, "notify_enabled", "0")
    assert db.notify_enabled(conn) is False


def test_is_seeded_defaults_false(conn):
    assert db.is_seeded(conn) is False
    db.set_setting(conn, "seeded", "1")
    assert db.is_seeded(conn) is True


def test_newest_ts_and_counts(conn):
    assert db.newest_ts(conn) is None
    assert db.cameras_reporting(conn, 0) == 0

    db.save_camera(conn, "cam_a", "1920x1080", 0.0, 0, 30)
    db.save_camera(conn, "cam_b", "1280x720", 0.0, 0, 30)
    db.add_sample(conn, "cam_a", 10, 18.0, 200.0)
    db.add_sample(conn, "cam_a", 30, 22.0, 400.0)
    db.add_sample(conn, "cam_b", 30, 19.0, 300.0)

    assert db.newest_ts(conn) == 30
    assert db.camera_count(conn) == 2
    assert db.cameras_reporting(conn, 20) == 2
    assert db.cameras_reporting(conn, 31) == 0


def test_latest_notification_none_then_row(conn):
    assert db.latest_notification(conn) is None

    db.add_notification(conn, 100, "cam_a", "1920x1080", 5.0, 500.0, 1, True, None)
    db.add_notification(conn, 200, "cam_b", "1920x1080", 4.0, 400.0, 1, False, "boom")

    latest = db.latest_notification(conn)
    assert latest["ts"] == 200
    assert latest["error"] == "boom"


def test_file_size_counts_wal(db_path):
    assert db.file_size(db_path) > 0
