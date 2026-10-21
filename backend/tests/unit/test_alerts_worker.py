"""Alert worker: state persistence, one cycle, hot reload, IST clock."""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from app.alerts import worker
from app.alerts.config import AlertConfig, Rule, SMTPSettings
from app.alerts.evaluator import RuleState

NOW = dt.datetime(2026, 10, 21, 16, 0, 0)
SETTINGS = SMTPSettings(
    server="smtp.internal", port=25, sender="noreply@example.com",
    recipients=("ops@example.com",),
)


def config(rule: Rule) -> AlertConfig:
    return AlertConfig(rules=(rule,), timezone="Asia/Kolkata",
                       dashboard_url="http://dash.local")


def test_parse_now_naive_and_aware():
    assert worker.parse_now("2026-10-21 16:30", "Asia/Kolkata") == dt.datetime(
        2026, 10, 21, 16, 30)
    assert worker.parse_now("2026-10-21T11:00:00Z", "Asia/Kolkata") == dt.datetime(
        2026, 10, 21, 16, 30)


def test_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = {"blink|S1": RuleState(
        consecutive=2, firing=True, last_fired_at=NOW, last_value=12)}

    worker.save_state(path, state)
    loaded = worker.load_state(path)

    assert loaded["blink|S1"].firing is True
    assert loaded["blink|S1"].consecutive == 2
    assert loaded["blink|S1"].last_fired_at == NOW
    assert loaded["blink|S1"].last_value == 12


def test_corrupt_state_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert worker.load_state(path) == {}


def test_run_cycle_sends_alert_and_persists(monkeypatch, tmp_path):
    rule = Rule("blink", "blink_requests", "S1", 5, 10, breaches_required=1)
    calls: list[tuple] = []
    monkeypatch.setattr(
        worker.emailer, "send_alerts",
        lambda triggers, smtp, cfg, now, dry_run: calls.append(
            ("alert", len(triggers), dry_run)) or ["subject"])
    monkeypatch.setattr(worker.emailer, "send_recoveries", lambda *a, **k: [])

    state_path = tmp_path / "state.json"
    heartbeat_path = tmp_path / "heartbeat"

    triggers, recoveries = worker.run_cycle(
        config(rule), SETTINGS, NOW, state_path, heartbeat_path,
        counts_by_window={5: pd.DataFrame([{"SOURCE": "S1", "BLINK": 11}])},
    )

    assert len(triggers) == 1 and recoveries == []
    assert calls == [("alert", 1, False)]
    assert json.loads(state_path.read_text())["blink|S1"]["firing"] is True
    assert heartbeat_path.exists()


def test_run_cycle_respects_cooldown_across_restarts(monkeypatch, tmp_path):
    rule = Rule("blink", "blink_requests", "S1", 5, 10, breaches_required=1)
    calls: list[int] = []
    monkeypatch.setattr(
        worker.emailer, "send_alerts",
        lambda triggers, smtp, cfg, now, dry_run: calls.append(len(triggers)) or ["s"])
    monkeypatch.setattr(worker.emailer, "send_recoveries", lambda *a, **k: [])

    state_path = tmp_path / "state.json"
    heartbeat_path = tmp_path / "heartbeat"
    counts = {5: pd.DataFrame([{"SOURCE": "S1", "BLINK": 11}])}

    worker.run_cycle(config(rule), SETTINGS, NOW, state_path, heartbeat_path,
                     counts_by_window=counts)
    worker.run_cycle(config(rule), SETTINGS, NOW + dt.timedelta(minutes=1),
                     state_path, heartbeat_path, counts_by_window=counts)

    assert calls == [1]


def test_run_cycle_sends_recovery(monkeypatch, tmp_path):
    rule = Rule("blink", "blink_requests", "S1", 5, 10, breaches_required=1)
    state_path = tmp_path / "state.json"
    heartbeat_path = tmp_path / "heartbeat"
    worker.save_state(state_path, {"blink|S1": RuleState(
        firing=True, last_value=12, last_fired_at=NOW - dt.timedelta(minutes=1))})

    recoveries_sent: list[int] = []
    monkeypatch.setattr(worker.emailer, "send_alerts", lambda *a, **k: [])
    monkeypatch.setattr(
        worker.emailer, "send_recoveries",
        lambda items, *a, **k: recoveries_sent.append(len(items)) or ["resolve"])

    _, recoveries = worker.run_cycle(
        config(rule), SETTINGS, NOW, state_path, heartbeat_path,
        counts_by_window={5: pd.DataFrame([{"SOURCE": "S1", "BLINK": 5}])},
    )

    assert len(recoveries) == 1
    assert recoveries_sent == [1]
    assert json.loads(state_path.read_text())["blink|S1"]["firing"] is False


def test_reload_keeps_last_good_config(tmp_path):
    path = tmp_path / "alerts.yaml"
    path.write_text(
        "rules:\n  - id: a\n    metric: total\n    window_minutes: 5\n    threshold: 1\n",
        encoding="utf-8")
    current = worker.load_config(path)

    path.write_text("rules: [", encoding="utf-8")
    assert worker.reload_config(str(path), current) == current

    path.write_text(
        "rules:\n  - id: b\n    metric: total\n    window_minutes: 5\n    threshold: 2\n",
        encoding="utf-8")
    reloaded = worker.reload_config(str(path), current)
    assert reloaded.rules[0].id == "b"


def test_dry_run_renders_without_smtp(monkeypatch, tmp_path):
    path = tmp_path / "alerts.yaml"
    path.write_text(
        "evaluation_interval_seconds: 60\n"
        "rules:\n  - id: a\n    metric: total\n    window_minutes: 5\n    threshold: 1\n",
        encoding="utf-8")
    monkeypatch.delenv("SMTP_SERVER", raising=False)
    monkeypatch.setattr(worker, "fetch_counts",
                        lambda table, now, window: pd.DataFrame([{"SOURCE": "S1", "TOTAL": 1}]))
    monkeypatch.setattr(worker.emailer, "send_alerts", lambda *a, **k: [])
    monkeypatch.setattr(worker.emailer, "send_recoveries", lambda *a, **k: [])

    assert worker.main([
        "--config", str(path), "--once", "--dry-run",
        "--now", "2026-10-21 16:00",
        "--state-file", str(tmp_path / "state.json"),
        "--heartbeat-file", str(tmp_path / "hb"),
    ]) == 0
