import json
from pathlib import Path

import pytest

import monitor

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "monitors.json").read_text()
)
ENTRIES = FIXTURE["monitors"]
LIVE = [entry for entry in ENTRIES if not entry["Monitor"].get("Deleted")]
DELETED = [entry for entry in ENTRIES if entry["Monitor"].get("Deleted")]


def camera(item):
    parsed = monitor.extract(item)
    assert parsed is not None
    return parsed


def entry(monitor_fields=None, status_fields=None, drop_status=False):
    data = {
        "Monitor": {
            "Id": 1,
            "Name": "Monitor-1",
            "Deleted": False,
            "Path": "rtsp://192.0.2.10:554/stream",
            "Type": "Ffmpeg",
            "Width": 1920,
            "Height": 1080,
        },
        "Monitor_Status": {
            "CaptureFPS": "25.00",
            "CaptureBandwidth": 102400,
            "Status": "Connected",
        },
    }
    data["Monitor"].update(monitor_fields or {})
    if drop_status:
        del data["Monitor_Status"]
    else:
        data["Monitor_Status"].update(status_fields or {})
    return data


def test_deleted_monitors_return_none():
    assert DELETED
    for item in DELETED:
        assert monitor.extract(item) is None


@pytest.mark.parametrize("item", LIVE, ids=lambda item: item["Monitor"]["Name"])
def test_live_fixture_entries_map_to_cameras(item):
    parsed = camera(item)
    raw = item["Monitor"]
    status = item["Monitor_Status"]

    assert parsed.source == raw["Name"]
    assert parsed.resolution == f"{raw['Width']}x{raw['Height']}"
    assert parsed.fps == float(status["CaptureFPS"])
    assert parsed.bandwidth_kb == round(status["CaptureBandwidth"] / 1024, 1)
    assert parsed.monitor_id == raw["Id"]
    assert parsed.connected is True


def test_capture_fps_string_is_coerced():
    assert camera(entry(status_fields={"CaptureFPS": "30.49"})).fps == 30.49


def test_source_uses_name():
    assert camera(entry({"Name": "front-door"})).source == "front-door"


def test_source_falls_back_to_path():
    assert camera(entry({"Name": None})).source == "rtsp://192.0.2.10:554/stream"


def test_source_falls_back_to_type():
    assert camera(entry({"Name": None, "Path": ""})).source == "Ffmpeg"


def test_resolution_from_dimensions():
    assert camera(entry()).resolution == "1920x1080"


def test_missing_dimensions_give_dash():
    assert camera(entry({"Width": 0, "Height": 0})).resolution == "-"


def test_missing_status_gives_zero_fps():
    parsed = camera(entry(drop_status=True))

    assert parsed.fps == 0.0
    assert parsed.bandwidth_kb == 0.0
    assert parsed.connected is False


def test_bandwidth_converted_to_kb():
    assert camera(entry(status_fields={"CaptureBandwidth": 448101})).bandwidth_kb == 437.6


def test_null_fields_do_not_raise():
    parsed = camera(entry(
        {"Width": None, "Height": None},
        {"CaptureFPS": None, "CaptureBandwidth": None, "Status": None},
    ))

    assert parsed.resolution == "-"
    assert parsed.fps == 0.0
    assert parsed.bandwidth_kb == 0.0
    assert parsed.connected is False


def test_disconnected_status_is_reported():
    assert camera(entry(status_fields={"Status": "Disconnected"})).connected is False


def test_missing_id_gives_none():
    assert camera(entry({"Id": None})).monitor_id is None
