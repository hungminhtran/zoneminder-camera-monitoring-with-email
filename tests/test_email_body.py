import monitor

ALERTS = [
    {
        "source": "cam-a",
        "resolution": "1920x1080",
        "avg_fps": 5.0,
        "bandwidth_kb": 512.26,
    }
]


def test_no_alerts_give_empty_body():
    assert monitor.build_email_body([], 0, 18.0) == ""


def test_header_states_count_and_threshold():
    body = monitor.build_email_body(ALERTS * 2, 0, 18.0)

    assert "2 camera(s)" in body
    assert "18 fps" in body


def test_one_block_per_camera():
    body = monitor.build_email_body(ALERTS * 3, 0, 18.0)

    assert body.count("Source     :") == 3


def test_values_are_formatted():
    body = monitor.build_email_body(ALERTS, 0, 18.0)

    assert "Avg FPS    : 5.00" in body
    assert "Bandwidth  : 512.3 KB/s" in body


def test_timestamp_uses_display_timezone():
    body = monitor.build_email_body(ALERTS, 1_700_000_000, 18.0, "Asia/Ho_Chi_Minh")

    assert "2023-11-15 05:13:20 +0700" in body
