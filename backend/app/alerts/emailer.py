"""SMTP delivery and email rendering for load alerts.

Uses the same plain-SMTP contract as the standalone AIKYC service; optional
STARTTLS/SSL/auth are available through ``SMTPSettings`` but default off.
"""
from __future__ import annotations

import datetime as dt
import html
import smtplib
from email.message import EmailMessage

from .config import AlertConfig, SMTPSettings
from .evaluator import Recovery, Trigger


def _clean_header(value: str) -> str:
    """Flatten CR/LF so rule/source text cannot inject headers."""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def _fmt_ts(when: dt.datetime, timezone: str) -> str:
    return f"{when.strftime('%Y-%m-%d %H:%M:%S')} {timezone}"


def _recipients(rule_recipients: tuple[str, ...], settings: SMTPSettings) -> tuple[str, ...]:
    return rule_recipients or settings.recipients


def build_alert(
    triggers: list[Trigger],
    now: dt.datetime,
    config: AlertConfig,
) -> tuple[str, str, str]:
    if len(triggers) == 1:
        item = triggers[0]
        subject = (
            f"[ui-dashboard][ALERT] {item.rule.label} {item.value:,} > "
            f"{item.threshold:,} in {item.rule.window_minutes}m ({item.source})"
        )
    else:
        subject = f"[ui-dashboard][ALERT] {len(triggers)} load thresholds breached"

    lines = ["ui-dashboard load alert", f"Time: {_fmt_ts(now, config.timezone)}", ""]
    for item in triggers:
        lines.extend([
            f"Rule: {item.rule.id}",
            f"Metric: {item.rule.label}",
            f"Source: {item.source}",
            f"Window: last {item.rule.window_minutes} minutes",
            f"Observed: {item.value:,}",
            f"Threshold: {item.threshold:,}",
            "",
        ])
    lines.append(f"Dashboard: {config.dashboard_url}")
    text = "\n".join(lines)

    rows = "".join(
        "<tr>"
        f"<td>{html.escape(item.rule.label)}</td>"
        f"<td>{html.escape(item.source)}</td>"
        f"<td>{item.value:,}</td>"
        f"<td>{item.threshold:,}</td>"
        f"<td>{item.rule.window_minutes}m</td>"
        "</tr>"
        for item in triggers
    )
    html_body = (
        "<html><body>"
        "<h2>ui-dashboard load alert</h2>"
        f"<p><strong>Time:</strong> {html.escape(_fmt_ts(now, config.timezone))}</p>"
        '<table border="1" cellpadding="6" cellspacing="0">'
        "<thead><tr><th>Metric</th><th>Source</th><th>Observed</th>"
        "<th>Threshold</th><th>Window</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f'<p><a href="{html.escape(config.dashboard_url, quote=True)}">'
        "Open the dashboard</a></p>"
        "</body></html>"
    )
    return subject, text, html_body


def build_recovery(
    recoveries: list[Recovery],
    now: dt.datetime,
    config: AlertConfig,
) -> tuple[str, str, str]:
    if len(recoveries) == 1:
        item = recoveries[0]
        subject = f"[ui-dashboard][RESOLVED] {item.rule.label} ({item.source})"
    else:
        subject = f"[ui-dashboard][RESOLVED] {len(recoveries)} load alerts cleared"

    lines = ["ui-dashboard load alert resolved", f"Time: {_fmt_ts(now, config.timezone)}", ""]
    for item in recoveries:
        lines.extend([
            f"Rule: {item.rule.id}",
            f"Metric: {item.rule.label}",
            f"Source: {item.source}",
            f"Window: last {item.rule.window_minutes} minutes",
            f"Observed: {item.value:,}",
            f"Threshold: {item.threshold:,}",
            "",
        ])
    lines.append(f"Dashboard: {config.dashboard_url}")
    text = "\n".join(lines)

    rows = "".join(
        "<tr>"
        f"<td>{html.escape(item.rule.label)}</td>"
        f"<td>{html.escape(item.source)}</td>"
        f"<td>{item.value:,}</td>"
        f"<td>{item.threshold:,}</td>"
        "</tr>"
        for item in recoveries
    )
    html_body = (
        "<html><body>"
        "<h2>ui-dashboard load alert resolved</h2>"
        f"<p><strong>Time:</strong> {html.escape(_fmt_ts(now, config.timezone))}</p>"
        '<table border="1" cellpadding="6" cellspacing="0">'
        "<thead><tr><th>Metric</th><th>Source</th><th>Observed</th>"
        "<th>Threshold</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f'<p><a href="{html.escape(config.dashboard_url, quote=True)}">'
        "Open the dashboard</a></p>"
        "</body></html>"
    )
    return subject, text, html_body


def build_test(now: dt.datetime, config: AlertConfig) -> tuple[str, str, str]:
    subject = "[ui-dashboard][TEST] SMTP alert delivery"
    text = (
        "This is a test email from the ui-dashboard alert worker.\n"
        f"Time: {_fmt_ts(now, config.timezone)}\n"
        f"Dashboard: {config.dashboard_url}\n"
    )
    html_body = (
        "<html><body>"
        "<h2>ui-dashboard SMTP test</h2>"
        "<p>This is a test email from the ui-dashboard alert worker.</p>"
        f"<p><strong>Time:</strong> {html.escape(_fmt_ts(now, config.timezone))}</p>"
        f'<p><a href="{html.escape(config.dashboard_url, quote=True)}">'
        "Open the dashboard</a></p>"
        "</body></html>"
    )
    return subject, text, html_body


def send(
    subject: str,
    text: str,
    html_body: str,
    recipients: tuple[str, ...],
    settings: SMTPSettings,
    dry_run: bool = False,
) -> None:
    message = EmailMessage()
    message["From"] = _clean_header(settings.sender)
    message["To"] = ", ".join(_clean_header(r) for r in recipients)
    message["Subject"] = _clean_header(subject)
    message.set_content(text)
    message.add_alternative(html_body, subtype="html")

    if dry_run:
        return

    if settings.use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.server, settings.port, timeout=15)
    else:
        server = smtplib.SMTP(settings.server, settings.port, timeout=15)

    try:
        if settings.starttls:
            server.starttls()
        if settings.username:
            server.login(settings.username, settings.password)
        server.send_message(
            message, from_addr=settings.sender, to_addrs=list(recipients))
    finally:
        try:
            server.quit()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass


def send_alerts(
    triggers: list[Trigger],
    settings: SMTPSettings,
    config: AlertConfig,
    now: dt.datetime,
    dry_run: bool = False,
) -> list[str]:
    groups: dict[tuple[str, ...], list[Trigger]] = {}
    for item in triggers:
        groups.setdefault(_recipients(item.rule.recipients, settings), []).append(item)

    subjects: list[str] = []
    for recipients, items in groups.items():
        subject, text, html_body = build_alert(items, now, config)
        send(subject, text, html_body, recipients, settings, dry_run)
        subjects.append(subject)
    return subjects


def send_recoveries(
    recoveries: list[Recovery],
    settings: SMTPSettings,
    config: AlertConfig,
    now: dt.datetime,
    dry_run: bool = False,
) -> list[str]:
    groups: dict[tuple[str, ...], list[Recovery]] = {}
    for item in recoveries:
        groups.setdefault(_recipients(item.rule.recipients, settings), []).append(item)

    subjects: list[str] = []
    for recipients, items in groups.items():
        subject, text, html_body = build_recovery(items, now, config)
        send(subject, text, html_body, recipients, settings, dry_run)
        subjects.append(subject)
    return subjects


def send_test(
    settings: SMTPSettings,
    config: AlertConfig,
    now: dt.datetime,
    dry_run: bool = False,
) -> str:
    subject, text, html_body = build_test(now, config)
    send(subject, text, html_body, settings.recipients, settings, dry_run)
    return subject
