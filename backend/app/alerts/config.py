"""Alert rule configuration and SMTP settings.

Rules are read from a YAML file (``ALERT_CONFIG``, default ``alerts.yaml``).
The worker re-reads that file every cycle; a broken file keeps the last good
rule set.

SMTP mirrors the standalone AIKYC service: ``SMTP_SERVER``, ``SMTP_PORT``,
``EMAIL_SENDER`` and ``EMAIL_RECIVER`` (sic), plain SMTP without auth by
default. ``SMTP_STARTTLS`` / ``SMTP_SSL`` and ``SMTP_USERNAME`` /
``SMTP_PASSWORD`` are optional for other relays.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

METRIC_COLUMNS: dict[str, str] = {
    "total": "TOTAL",
    "blink_requests": "BLINK",
    "head_nod_requests": "HEAD_NOD",
    "authenticity_requests": "AUTH",
    "image_seg_requests": "IMAGE_SEG",
    "verify_token_requests": "VERIFYTOKEN",
    "callback_requests": "CALLBACK",
}

METRIC_LABELS: dict[str, str] = {
    "total": "Total transactions",
    "blink_requests": "Blink requests",
    "head_nod_requests": "Head Nod requests",
    "authenticity_requests": "Authenticity requests",
    "image_seg_requests": "Image Seg requests",
    "verify_token_requests": "Verify Token requests",
    "callback_requests": "Callback requests",
}

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_DASHBOARD_URL = "http://localhost:8090"
DEFAULT_CONFIG_PATH = os.getenv("ALERT_CONFIG", "alerts.yaml")

_RECIPIENT_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+$")


class ConfigError(ValueError):
    """Invalid alert configuration."""


@dataclass(frozen=True)
class Rule:
    id: str
    metric: str
    source: str | None
    window_minutes: int
    threshold: int
    breaches_required: int = 2
    cooldown_minutes: int = 15
    recipients: tuple[str, ...] = ()
    enabled: bool = True

    @property
    def column(self) -> str:
        return METRIC_COLUMNS[self.metric]

    @property
    def label(self) -> str:
        return METRIC_LABELS[self.metric]


@dataclass(frozen=True)
class AlertConfig:
    rules: tuple[Rule, ...]
    evaluation_interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    timezone: str = DEFAULT_TIMEZONE
    dashboard_url: str = DEFAULT_DASHBOARD_URL

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass(frozen=True)
class SMTPSettings:
    server: str
    port: int
    sender: str
    recipients: tuple[str, ...] = field(default_factory=tuple)
    starttls: bool = False
    use_ssl: bool = False
    username: str = ""
    password: str = ""


def _as_int(value: object, field_name: str, *, minimum: int | None = None) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field_name} must be an integer, got {value!r}") from exc
    if minimum is not None and number < minimum:
        raise ConfigError(f"{field_name} must be >= {minimum}, got {number}")
    return number


def _as_bool(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    raise ConfigError(f"{field_name} must be a boolean, got {value!r}")


def _parse_recipients(value: object, field_name: str) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        items: list[object] = re.split(r"[,;]", value)
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise ConfigError(f"{field_name} must be a string or list")

    recipients: list[str] = []
    for item in items:
        address = str(item).strip()
        if not address:
            continue
        if "\r" in address or "\n" in address or not _RECIPIENT_RE.match(address):
            raise ConfigError(f"{field_name} contains an invalid address: {address!r}")
        recipients.append(address)
    return tuple(recipients)


def _parse_rule(raw: object, index: int, seen_ids: set[str]) -> Rule:
    if not isinstance(raw, dict):
        raise ConfigError(f"rules[{index}] must be a mapping")

    rule_id = str(raw.get("id") or "").strip()
    if not rule_id:
        raise ConfigError(f"rules[{index}].id is required")
    if rule_id in seen_ids:
        raise ConfigError(f"duplicate rule id {rule_id!r}")
    seen_ids.add(rule_id)

    metric = str(raw.get("metric") or "").strip()
    if metric not in METRIC_COLUMNS:
        raise ConfigError(
            f"rule {rule_id!r}: unknown metric {metric!r}; "
            f"expected one of {sorted(METRIC_COLUMNS)}")

    source_raw = raw.get("source")
    source = str(source_raw).strip() if source_raw not in (None, "") else None
    if source == "":
        source = None

    return Rule(
        id=rule_id,
        metric=metric,
        source=source,
        window_minutes=_as_int(raw.get("window_minutes"), f"rule {rule_id}.window_minutes",
                               minimum=1),
        threshold=_as_int(raw.get("threshold"), f"rule {rule_id}.threshold", minimum=0),
        breaches_required=_as_int(raw.get("breaches_required", 2),
                                  f"rule {rule_id}.breaches_required", minimum=1),
        cooldown_minutes=_as_int(raw.get("cooldown_minutes", 15),
                                 f"rule {rule_id}.cooldown_minutes", minimum=0),
        recipients=_parse_recipients(raw.get("recipients"), f"rule {rule_id}.recipients"),
        enabled=_as_bool(raw.get("enabled", True), f"rule {rule_id}.enabled"),
    )


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AlertConfig:
    """Load and validate the YAML rule file."""
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"alert config not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} must contain a mapping")

    tz_name = str(os.getenv("ALERT_TIMEZONE") or raw.get("timezone") or DEFAULT_TIMEZONE).strip()
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"unknown timezone {tz_name!r}") from exc

    raw_rules = raw.get("rules") or []
    if not isinstance(raw_rules, list):
        raise ConfigError("rules must be a list")

    seen_ids: set[str] = set()
    rules = tuple(_parse_rule(item, index, seen_ids) for index, item in enumerate(raw_rules))

    return AlertConfig(
        rules=rules,
        evaluation_interval_seconds=_as_int(
            raw.get("evaluation_interval_seconds", DEFAULT_INTERVAL_SECONDS),
            "evaluation_interval_seconds", minimum=1),
        timezone=tz_name,
        dashboard_url=str(os.getenv("DASHBOARD_URL") or raw.get("dashboard_url")
                          or DEFAULT_DASHBOARD_URL).strip(),
    )


def load_smtp_settings() -> SMTPSettings:
    """SMTP settings from the environment (same contract as standalone AIKYC)."""
    server = os.getenv("SMTP_SERVER", "").strip()
    if not server:
        raise ConfigError("SMTP_SERVER is required")
    port = _as_int(os.getenv("SMTP_PORT", "25"), "SMTP_PORT", minimum=1)

    sender = os.getenv("EMAIL_SENDER", "").strip()
    if not sender:
        raise ConfigError("EMAIL_SENDER is required")
    if "\r" in sender or "\n" in sender or not _RECIPIENT_RE.match(sender):
        raise ConfigError(f"EMAIL_SENDER is not a valid address: {sender!r}")

    raw_recipients = os.getenv("EMAIL_RECIVER") or os.getenv("EMAIL_RECEIVER") or ""
    recipients = _parse_recipients(raw_recipients, "EMAIL_RECIVER")
    if not recipients:
        raise ConfigError("EMAIL_RECIVER (or EMAIL_RECEIVER) is required")

    starttls = _as_bool(os.getenv("SMTP_STARTTLS"), "SMTP_STARTTLS")
    use_ssl = _as_bool(os.getenv("SMTP_SSL"), "SMTP_SSL")
    if starttls and use_ssl:
        raise ConfigError("SMTP_STARTTLS and SMTP_SSL are mutually exclusive")

    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if password and not username:
        raise ConfigError("SMTP_PASSWORD requires SMTP_USERNAME")

    return SMTPSettings(
        server=server,
        port=port,
        sender=sender,
        recipients=recipients,
        starttls=starttls,
        use_ssl=use_ssl,
        username=username,
        password=password,
    )
