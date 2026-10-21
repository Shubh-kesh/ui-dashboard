"""Alert config parsing and SMTP environment contract."""
from __future__ import annotations

import textwrap

import pytest

from app.alerts import config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "SMTP_SERVER", "SMTP_PORT", "EMAIL_SENDER", "EMAIL_RECIVER",
        "EMAIL_RECEIVER", "SMTP_STARTTLS", "SMTP_SSL", "SMTP_USERNAME",
        "SMTP_PASSWORD", "ALERT_TIMEZONE", "DASHBOARD_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def _write(tmp_path, body: str):
    path = tmp_path / "alerts.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_loads_rules_and_defaults(tmp_path):
    path = _write(tmp_path, """
        evaluation_interval_seconds: 30
        timezone: Asia/Kolkata
        rules:
          - id: blink
            metric: blink_requests
            source: "*"
            window_minutes: 5
            threshold: 100
          - id: auth
            metric: authenticity_requests
            window_minutes: 10
            threshold: 50
            enabled: false
    """)

    cfg = config.load_config(path)

    assert cfg.evaluation_interval_seconds == 30
    assert cfg.timezone == "Asia/Kolkata"
    assert cfg.dashboard_url == config.DEFAULT_DASHBOARD_URL
    assert [rule.id for rule in cfg.rules] == ["blink", "auth"]

    blink, auth = cfg.rules
    assert blink.source == "*"
    assert blink.breaches_required == 2
    assert blink.cooldown_minutes == 15
    assert blink.enabled is True
    assert blink.column == "BLINK"

    assert auth.source is None
    assert auth.enabled is False
    assert auth.column == "AUTH"


def test_env_overrides_timezone_and_dashboard_url(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_TIMEZONE", "UTC")
    monkeypatch.setenv("DASHBOARD_URL", "https://dash.example.com")
    path = _write(tmp_path, """
        timezone: Asia/Kolkata
        rules: []
    """)

    cfg = config.load_config(path)

    assert cfg.timezone == "UTC"
    assert cfg.dashboard_url == "https://dash.example.com"


def test_rejects_unknown_metric(tmp_path):
    path = _write(tmp_path, """
        rules:
          - id: x
            metric: nope
            window_minutes: 5
            threshold: 1
    """)
    with pytest.raises(config.ConfigError, match="unknown metric"):
        config.load_config(path)


def test_rejects_bad_timezone(tmp_path):
    path = _write(tmp_path, "timezone: Mars/Olympus\nrules: []\n")
    with pytest.raises(config.ConfigError, match="unknown timezone"):
        config.load_config(path)


def test_rejects_duplicate_ids(tmp_path):
    path = _write(tmp_path, """
        rules:
          - id: x
            metric: total
            window_minutes: 5
            threshold: 1
          - id: x
            metric: total
            window_minutes: 5
            threshold: 1
    """)
    with pytest.raises(config.ConfigError, match="duplicate rule id"):
        config.load_config(path)


def test_rejects_invalid_recipient(tmp_path):
    path = _write(tmp_path, """
        rules:
          - id: x
            metric: total
            window_minutes: 5
            threshold: 1
            recipients: ["not-an-email"]
    """)
    with pytest.raises(config.ConfigError, match="invalid address"):
        config.load_config(path)


def test_smtp_settings_match_aikyc_env_contract(monkeypatch):
    monkeypatch.setenv("SMTP_SERVER", "smtp.internal")
    monkeypatch.setenv("SMTP_PORT", "25")
    monkeypatch.setenv("EMAIL_SENDER", "noreply@example.com")
    monkeypatch.setenv("EMAIL_RECIVER", "ops@example.com; oncall@example.com")

    settings = config.load_smtp_settings()

    assert settings.server == "smtp.internal"
    assert settings.port == 25
    assert settings.sender == "noreply@example.com"
    assert settings.recipients == ("ops@example.com", "oncall@example.com")
    assert settings.starttls is False
    assert settings.use_ssl is False


def test_smtp_receiver_alias(monkeypatch):
    monkeypatch.setenv("SMTP_SERVER", "smtp.internal")
    monkeypatch.setenv("EMAIL_SENDER", "noreply@example.com")
    monkeypatch.setenv("EMAIL_RECEIVER", "ops@example.com")

    assert config.load_smtp_settings().recipients == ("ops@example.com",)


def test_smtp_requires_server_and_recipients(monkeypatch):
    with pytest.raises(config.ConfigError, match="SMTP_SERVER"):
        config.load_smtp_settings()

    monkeypatch.setenv("SMTP_SERVER", "smtp.internal")
    monkeypatch.setenv("EMAIL_SENDER", "noreply@example.com")
    with pytest.raises(config.ConfigError, match="EMAIL_RECIVER"):
        config.load_smtp_settings()


def test_smtp_starttls_and_ssl_are_mutually_exclusive(monkeypatch):
    monkeypatch.setenv("SMTP_SERVER", "smtp.internal")
    monkeypatch.setenv("EMAIL_SENDER", "noreply@example.com")
    monkeypatch.setenv("EMAIL_RECIVER", "ops@example.com")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    monkeypatch.setenv("SMTP_SSL", "true")

    with pytest.raises(config.ConfigError, match="mutually exclusive"):
        config.load_smtp_settings()
