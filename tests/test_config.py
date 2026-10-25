import importlib

import pytest

import config


def test_required_returns_value(monkeypatch):
    monkeypatch.setenv("ZM_URL", "http://example/zm")
    assert config.required("ZM_URL") == "http://example/zm"


def test_required_trims_whitespace(monkeypatch):
    monkeypatch.setenv("ZM_URL", "  http://example/zm  ")
    assert config.required("ZM_URL") == "http://example/zm"


def test_required_exits_when_missing(monkeypatch):
    monkeypatch.delenv("ZM_URL", raising=False)
    with pytest.raises(SystemExit):
        config.required("ZM_URL")


def test_required_exits_when_empty(monkeypatch):
    monkeypatch.setenv("ZM_URL", "")
    with pytest.raises(SystemExit):
        config.required("ZM_URL")


def test_required_exits_when_whitespace_only(monkeypatch):
    monkeypatch.setenv("ZM_URL", "   ")
    with pytest.raises(SystemExit):
        config.required("ZM_URL")


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_flag_truthy(monkeypatch, value):
    monkeypatch.setenv("ZM_INSECURE", value)
    assert config.flag("ZM_INSECURE") is True


@pytest.mark.parametrize("value", ["0", "false", "", "maybe", "2"])
def test_flag_falsy(monkeypatch, value):
    monkeypatch.setenv("ZM_INSECURE", value)
    assert config.flag("ZM_INSECURE") is False


def test_flag_absent(monkeypatch):
    monkeypatch.delenv("ZM_INSECURE", raising=False)
    assert config.flag("ZM_INSECURE") is False


def test_defaults_when_unset(monkeypatch):
    for name in ("SAMPLE_SECONDS", "RETENTION_DAYS", "LOW_FPS_THRESHOLD", "DISPLAY_TZ"):
        monkeypatch.delenv(name, raising=False)
    reloaded = importlib.reload(config)
    try:
        assert reloaded.SAMPLE_SECONDS == 60
        assert reloaded.RETENTION_DAYS == 2.0
        assert reloaded.LOW_FPS_THRESHOLD == 18.0
        assert reloaded.DISPLAY_TZ == "Asia/Ho_Chi_Minh"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_tz_returns_zoneinfo():
    assert config.tz().key == config.DISPLAY_TZ
