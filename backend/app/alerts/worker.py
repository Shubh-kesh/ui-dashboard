"""Standalone alert worker: evaluate load rules and send SMTP emails.

Run as ``python -m app.alerts.worker`` (long-running, one replica) or with
``--once``/``--now`` for a single evaluation. It is deliberately separate from
the FastAPI process so alerts fire even when nobody has the dashboard open and
so replicas of the API cannot send duplicate mail.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import signal
import threading
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .. import db, queries
from ..config import get_settings
from . import emailer
from .config import (
    AlertConfig,
    ConfigError,
    SMTPSettings,
    load_config,
    load_smtp_settings,
)
from .evaluator import Recovery, RuleState, Trigger, evaluate

log = logging.getLogger("ui_dashboard.alerts")

DEFAULT_STATE_FILE = os.getenv(
    "ALERT_STATE_FILE", "/tmp/ui-dashboard-alerts-state.json")
DEFAULT_HEARTBEAT_FILE = os.getenv(
    "ALERT_HEARTBEAT_FILE", "/tmp/ui-dashboard-alerts-heartbeat")


def parse_now(value: str | None, timezone: str) -> dt.datetime:
    """Current naive wall-clock time in the configured timezone.

    Event timestamps are stored as naive IST datetimes, so everything the
    worker compares is also naive IST - independent of the MSSQL server clock.
    """
    tz = ZoneInfo(timezone)
    if not value:
        return dt.datetime.now(tz).replace(tzinfo=None)
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"invalid --now value {value!r}; use an ISO timestamp") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(tz)
    return parsed.replace(tzinfo=None)


def load_state(path: str | Path) -> dict[str, RuleState]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("could not read alert state %s: %s", path, exc)
        return {}
    if not isinstance(raw, dict):
        return {}

    state: dict[str, RuleState] = {}
    for key, value in raw.items():
        try:
            state[str(key)] = RuleState.from_dict(value if isinstance(value, dict) else {})
        except (TypeError, ValueError) as exc:
            log.warning("ignoring invalid alert state entry %s: %s", key, exc)
    return state


def save_state(path: str | Path, state: dict[str, RuleState]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps({key: value.to_dict() for key, value in state.items()},
                   indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(target)


def touch_heartbeat(path: str | Path, now: dt.datetime) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(now.isoformat(sep=" "), encoding="utf-8")


def fetch_counts(table: str, now: dt.datetime, window_minutes: int) -> pd.DataFrame:
    start = now - dt.timedelta(minutes=window_minutes)
    sql, params = queries.alert_counts_query(table, start, now)
    return db.fetch_df(sql, params)


def reload_config(config_path: str, current: AlertConfig) -> AlertConfig:
    """Re-read rules; keep the last good config if the file is broken."""
    try:
        reloaded = load_config(config_path)
    except (ConfigError, OSError) as exc:
        log.error("alert config reload failed; keeping last good config: %s", exc)
        return current
    if reloaded != current:
        log.info("alert config reloaded (%d rules)", len(reloaded.rules))
    return reloaded


def run_cycle(
    config: AlertConfig,
    smtp: SMTPSettings,
    now: dt.datetime,
    state_path: str | Path = DEFAULT_STATE_FILE,
    heartbeat_path: str | Path = DEFAULT_HEARTBEAT_FILE,
    dry_run: bool = False,
    counts_by_window: dict[int, pd.DataFrame] | None = None,
) -> tuple[list[Trigger], list[Recovery]]:
    """One evaluation pass. Exposed for tests and ``--once``."""
    state = load_state(state_path)

    if counts_by_window is None:
        windows = sorted({rule.window_minutes for rule in config.rules if rule.enabled})
        table = get_settings().table
        counts_by_window = {
            window: fetch_counts(table, now, window) for window in windows
        }

    triggers, recoveries = evaluate(config.rules, counts_by_window, state, now)

    if triggers:
        subjects = emailer.send_alerts(triggers, smtp, config, now, dry_run)
        for subject in subjects:
            log.warning("ALERT %s", subject)
    if recoveries:
        subjects = emailer.send_recoveries(recoveries, smtp, config, now, dry_run)
        for subject in subjects:
            log.info("RESOLVED %s", subject)

    save_state(state_path, state)
    touch_heartbeat(heartbeat_path, now)
    log.info(
        "alert cycle now=%s rules=%d triggers=%d recoveries=%d dry_run=%s",
        now.isoformat(sep=" "), len(config.rules), len(triggers), len(recoveries), dry_run,
    )
    return triggers, recoveries


def run_forever(
    config_path: str,
    smtp: SMTPSettings,
    state_path: str,
    heartbeat_path: str,
    dry_run: bool = False,
) -> None:
    config = load_config(config_path)  # fail fast on a bad initial config
    stop = threading.Event()

    def _handle(signum: int, _frame: object) -> None:
        log.info("received signal %s; shutting down", signum)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle)
        except ValueError:  # pragma: no cover - non-main thread
            pass

    while not stop.is_set():
        config = reload_config(config_path, config)

        now = parse_now(None, config.timezone)
        try:
            run_cycle(config, smtp, now, state_path, heartbeat_path, dry_run)
        except Exception:
            log.exception("alert cycle failed; retrying next interval")

        stop.wait(config.evaluation_interval_seconds)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LivePhoto dashboard load-alert worker")
    parser.add_argument("--config", default=os.getenv("ALERT_CONFIG", "alerts.yaml"),
                        help="path to alerts.yaml (default: %(default)s)")
    parser.add_argument("--once", action="store_true",
                        help="run one evaluation cycle and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="evaluate and log but do not send email")
    parser.add_argument("--test-email", action="store_true",
                        help="send a test email and exit")
    parser.add_argument("--now", default=None,
                        help="evaluate as of this ISO timestamp (testing)")
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    parser.add_argument("--heartbeat-file", default=DEFAULT_HEARTBEAT_FILE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = load_config(args.config)
    try:
        smtp = load_smtp_settings()
    except ConfigError:
        if not args.dry_run:
            raise
        smtp = SMTPSettings(
            server="dry-run", port=25, sender="dry-run@localhost",
            recipients=("dry-run@localhost",))
        log.warning("SMTP is not configured; --dry-run will only render emails")

    if not args.test_email:
        get_settings().validate_credentials()

    now = parse_now(args.now, config.timezone)

    if args.test_email:
        subject = emailer.send_test(smtp, config, now, args.dry_run)
        log.info("test email %s: %s",
                 "rendered (dry run)" if args.dry_run else "sent", subject)
        return 0

    if args.once or args.now:
        run_cycle(config, smtp, now, args.state_file, args.heartbeat_file, args.dry_run)
        return 0

    run_forever(args.config, smtp, args.state_file, args.heartbeat_file, args.dry_run)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
