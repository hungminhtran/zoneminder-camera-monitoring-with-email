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


@pytest.fixture
def fresh_config(monkeypatch):
    def load(**env):
        for key in ("DEV", "DB_DIR", "DB_PATH"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))
        return importlib.reload(config)

    yield load
    monkeypatch.undo()
    importlib.reload(config)


def test_tz_returns_zoneinfo():
    assert config.tz().key == config.DISPLAY_TZ


def test_default_database_lives_beside_the_project(fresh_config):
    reloaded = fresh_config()

    assert reloaded.DB_PATH.name == "prod_zoneminder_monitoring.db"
    assert reloaded.DB_PATH.parent == reloaded.SCRIPT_DIR.parent
    assert reloaded.DB_PATH.parent.name != "src"


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
def test_dev_flag_switches_the_database_name(fresh_config, value):
    reloaded = fresh_config(DEV=value)

    assert reloaded.ENV_NAME == "dev"
    assert reloaded.DB_PATH.name == "dev_zoneminder_monitoring.db"


@pytest.mark.parametrize("value", ["0", "false", ""])
def test_prod_name_when_dev_is_off(fresh_config, value):
    reloaded = fresh_config(DEV=value)

    assert reloaded.ENV_NAME == "prod"
    assert reloaded.DB_PATH.name == "prod_zoneminder_monitoring.db"


def test_db_dir_is_honoured(fresh_config, tmp_path):
    reloaded = fresh_config(DEV="1", DB_DIR=tmp_path)

    assert reloaded.DB_PATH == tmp_path / "dev_zoneminder_monitoring.db"


def test_explicit_db_path_wins(fresh_config, tmp_path):
    target = tmp_path / "custom.db"
    reloaded = fresh_config(DB_PATH=target)

    assert reloaded.DB_PATH == target
