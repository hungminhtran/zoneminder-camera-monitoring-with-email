import db
import web

NOW = 1_700_000_000.0
DAY = 86400


def add_sample(conn, source, ts, fps=20.0):
    db.add_sample(conn, source, ts, fps, 500.0)


def status(conn, size_samples=None):
    return web.build_status_payload(conn, NOW, size_samples or [])


def test_collector_alive_when_sample_is_fresh(conn):
    add_sample(conn, "cam_a", int(NOW) - 30)

    payload = status(conn)

    assert payload["collector_alive"] is True
    assert payload["stale_seconds"] == 30


def test_collector_stale_when_sample_is_old(conn):
    add_sample(conn, "cam_a", int(NOW) - 300)

    payload = status(conn)

    assert payload["collector_alive"] is False
    assert payload["stale_seconds"] == 300


def test_collector_unknown_without_samples(conn):
    payload = status(conn)

    assert payload["collector_alive"] is False
    assert payload["stale_seconds"] is None


def test_cameras_reporting_counts_only_recent_samples(conn):
    db.save_camera(conn, "cam_a", "1920x1080", 0.0, 0, int(NOW))
    db.save_camera(conn, "cam_b", "1280x720", 0.0, 0, int(NOW))
    add_sample(conn, "cam_a", int(NOW) - 60)
    add_sample(conn, "cam_b", int(NOW) - 300)

    payload = status(conn)

    assert payload["cameras_known"] == 2
    assert payload["cameras_reporting"] == 1


def test_notify_disabled_reported(conn):
    db.set_setting(conn, "notify_enabled", "0")

    assert status(conn)["notify_enabled"] is False


def test_notify_enabled_by_default(conn):
    assert status(conn)["notify_enabled"] is True


def test_seeded_flag_reported(conn):
    db.set_setting(conn, "seeded", "1")

    assert status(conn)["seeded"] is True


def test_last_email_none_without_notifications(conn):
    assert status(conn)["last_email"] is None


def test_last_email_reports_failure(conn):
    db.add_notification(conn, int(NOW) - 60, "cam_a", "1920x1080", 5.0, 500.0, 1, False, "smtp down")

    payload = status(conn)["last_email"]

    assert payload["source"] == "cam_a"
    assert payload["email_ok"] is False
    assert payload["error"] == "smtp down"


def test_databases_size_and_delta(conn):
    samples = [
        (int(NOW) - DAY, 7_600_000),
        (int(NOW) - 3600, 7_900_000),
        (int(NOW), 8_000_000),
    ]

    payload = status(conn, samples)["database"]

    assert payload["bytes"] == 8_000_000
    assert payload["delta"] == 400_000


def test_database_size_without_samples(conn):
    assert status(conn, [])["database"] == {"bytes": None, "delta": None}


def test_database_size_single_sample_has_no_delta(conn):
    payload = status(conn, [(int(NOW), 8_000_000)])["database"]

    assert payload["bytes"] == 8_000_000
    assert payload["delta"] is None


def test_database_trend_ignores_samples_older_than_seven_days(conn):
    samples = [
        (int(NOW) - 8 * DAY, 1_000),
        (int(NOW) - 3600, 8_000_000),
        (int(NOW), 8_100_000),
    ]

    payload = status(conn, samples)["database"]

    assert payload["bytes"] == 8_100_000
    assert payload["delta"] == 100_000


def test_status_carries_threshold_and_timezone(conn):
    payload = status(conn)

    assert payload["threshold"] == 18.0
    assert payload["tz"] == "Asia/Ho_Chi_Minh"
    assert payload["as_of"] == int(NOW)


def test_record_db_size_appends_first_sample():
    samples = []

    assert web.record_db_size(samples, NOW, 8_000_000) is True
    assert samples == [(int(NOW), 8_000_000)]


def test_record_db_size_skips_within_interval():
    samples = [(int(NOW) - 60, 8_000_000)]

    assert web.record_db_size(samples, NOW, 8_100_000) is False
    assert samples == [(int(NOW) - 60, 8_000_000)]


def test_record_db_size_appends_after_interval():
    samples = [(int(NOW) - 3600, 8_000_000)]

    assert web.record_db_size(samples, NOW, 8_100_000) is True
    assert samples[-1] == (int(NOW), 8_100_000)


def test_record_db_size_ignores_missing_file():
    samples = [(int(NOW) - 3600, 8_000_000)]

    assert web.record_db_size(samples, NOW, 0) is False
    assert len(samples) == 1
