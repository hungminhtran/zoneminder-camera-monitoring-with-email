import web


def series_rows(*items):
    return [
        {"source": item[0], "resolution": item[1], "ts": item[2], "fps": item[3],
         "bandwidth_kb": item[4], "monitor_id": item[5] if len(item) > 5 else None}
        for item in items
    ]


def test_groups_rows_by_source():
    payload = web.build_series_payload(
        series_rows(
            ("cam_a", "1920x1080", 10, 20.0, 500.0),
            ("cam_a", "1920x1080", 20, 21.0, 510.0),
            ("cam_b", "1280x720", 10, 22.0, 520.0),
        ),
        18.0,
        "Asia/Ho_Chi_Minh",
    )

    assert [camera["source"] for camera in payload["cameras"]] == ["cam_a", "cam_b"]
    assert len(payload["cameras"][0]["points"]) == 2
    assert len(payload["cameras"][1]["points"]) == 1


def test_cameras_are_sorted_by_source():
    payload = web.build_series_payload(
        series_rows(
            ("cam_c", "1920x1080", 10, 20.0, 500.0),
            ("cam_a", "1920x1080", 10, 20.0, 500.0),
            ("cam_b", "1920x1080", 10, 20.0, 500.0),
        ),
        18.0,
        "UTC",
    )

    assert [camera["source"] for camera in payload["cameras"]] == ["cam_a", "cam_b", "cam_c"]


def test_cameras_are_ordered_by_monitor_id():
    payload = web.build_series_payload(
        series_rows(
            ("cam_ten", "1920x1080", 10, 20.0, 500.0, 10),
            ("cam_two", "1920x1080", 10, 20.0, 500.0, 2),
        ),
        18.0,
        "UTC",
    )

    assert [camera["source"] for camera in payload["cameras"]] == ["cam_two", "cam_ten"]


def test_cameras_without_monitor_id_sort_last():
    payload = web.build_series_payload(
        series_rows(
            ("cam_a", "1920x1080", 10, 20.0, 500.0),
            ("cam_z", "1920x1080", 10, 20.0, 500.0, 5),
        ),
        18.0,
        "UTC",
    )

    assert [camera["source"] for camera in payload["cameras"]] == ["cam_z", "cam_a"]


def test_resolution_carried_through():
    payload = web.build_series_payload(
        series_rows(("cam_a", "2688x1520", 10, 20.0, 500.0)), 18.0, "UTC"
    )

    assert payload["cameras"][0]["resolution"] == "2688x1520"


def test_values_are_rounded():
    payload = web.build_series_payload(
        series_rows(("cam_a", "1920x1080", 10, 30.489999, 1023.987)), 18.0, "UTC"
    )

    assert payload["cameras"][0]["points"] == [[10, 30.49, 1024.0]]


def test_threshold_and_timezone_present():
    payload = web.build_series_payload([], 18.0, "Asia/Ho_Chi_Minh")

    assert payload["threshold"] == 18.0
    assert payload["tz"] == "Asia/Ho_Chi_Minh"


def test_empty_rows_give_empty_camera_list():
    payload = web.build_series_payload([], 18.0, "UTC")

    assert payload["cameras"] == []


def test_points_keep_timestamp_width_and_order():
    payload = web.build_series_payload(
        series_rows(
            ("cam_a", "1920x1080", 1700000060, 19.5, 400.0),
            ("cam_a", "1920x1080", 1700000000, 18.5, 300.0),
        ),
        18.0,
        "UTC",
    )

    assert payload["cameras"][0]["points"] == [
        [1700000060, 19.5, 400.0],
        [1700000000, 18.5, 300.0],
    ]
