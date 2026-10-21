"""Email rendering and plain-SMTP delivery."""
from __future__ import annotations

import datetime as dt

from app.alerts import emailer
from app.alerts.config import AlertConfig, Rule, SMTPSettings
from app.alerts.evaluator import Recovery, Trigger

NOW = dt.datetime(2026, 10, 21, 16, 0, 0)


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sent = None
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def send_message(self, message, from_addr=None, to_addrs=None):
        self.sent = (message, from_addr, to_addrs)

    def quit(self):
        self.quit_called = True


def settings(**overrides) -> SMTPSettings:
    values = dict(
        server="smtp.internal",
        port=25,
        sender="noreply@example.com",
        recipients=("ops@example.com",),
    )
    values.update(overrides)
    return SMTPSettings(**values)


def config(*rules: Rule) -> AlertConfig:
    return AlertConfig(
        rules=rules or (),
        timezone="Asia/Kolkata",
        dashboard_url="http://dash.local",
    )


def plain_text(message) -> str:
    return message.get_body(preferencelist=("plain",)).get_content()


def html_text(message) -> str:
    return message.get_body(preferencelist=("html",)).get_content()


def test_send_uses_the_aikyc_plain_smtp_contract(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)

    emailer.send(
        "subject", "hello", "<p>hello</p>", ("ops@example.com",), settings())

    server = FakeSMTP.instances[0]
    assert (server.host, server.port) == ("smtp.internal", 25)
    message, from_addr, to_addrs = server.sent
    assert from_addr == "noreply@example.com"
    assert to_addrs == ["ops@example.com"]
    assert str(message["Subject"]) == "subject"
    assert "hello" in plain_text(message)
    assert "<p>hello</p>" in html_text(message)
    assert server.quit_called is True


def test_dry_run_does_not_connect(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)

    emailer.send("subject", "body", "<p>body</p>", ("ops@example.com",),
                 settings(), dry_run=True)

    assert FakeSMTP.instances == []


def test_header_injection_is_flattened(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)

    emailer.send("hello\r\nBcc: evil@example.com", "body", "<p>body</p>",
                 ("ops@example.com",), settings())

    message = FakeSMTP.instances[0].sent[0]
    assert "\n" not in str(message["Subject"])
    assert "Bcc" not in [name for name, _ in message.items()]


def test_build_alert_for_one_breach():
    rule = Rule("blink", "blink_requests", "S1", 5, 1000)
    subject, text, html_body = emailer.build_alert(
        [Trigger(rule, "S1", 1204, 1000)], NOW, config(rule))

    assert subject == "[ui-dashboard][ALERT] Blink requests 1,204 > 1,000 in 5m (S1)"
    assert "2026-10-21 16:00:00 Asia/Kolkata" in text
    assert "Observed: 1,204" in text
    assert "1,204" in html_body and "S1" in html_body


def test_build_alert_for_multiple_breaches():
    blink = Rule("blink", "blink_requests", "*", 5, 1000)
    auth = Rule("auth", "authenticity_requests", "S1", 5, 500)
    subject, text, _ = emailer.build_alert(
        [Trigger(blink, "all sources", 1204, 1000),
         Trigger(auth, "S1", 650, 500)],
        NOW, config(blink, auth))

    assert subject == "[ui-dashboard][ALERT] 2 load thresholds breached"
    assert "Blink requests" in text and "Authenticity requests" in text


def test_build_recovery():
    rule = Rule("blink", "blink_requests", "S1", 5, 1000)
    subject, text, html_body = emailer.build_recovery(
        [Recovery(rule, "S1", 800, 1000)], NOW, config(rule))

    assert subject == "[ui-dashboard][RESOLVED] Blink requests (S1)"
    assert "Observed: 800" in text
    assert "RESOLVED" not in html_body  # heading is human-readable
    assert "resolved" in html_body


def test_per_rule_recipients_override_global(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)

    rule_a = Rule("a", "total", None, 5, 1, recipients=("a@example.com",))
    rule_b = Rule("b", "total", None, 5, 1)
    triggers = [
        Trigger(rule_a, "all sources", 2, 1),
        Trigger(rule_b, "all sources", 2, 1),
    ]

    emailer.send_alerts(triggers, settings(), config(rule_a, rule_b), NOW)

    assert len(FakeSMTP.instances) == 2
    recipient_sets = {tuple(server.sent[2]) for server in FakeSMTP.instances}
    assert recipient_sets == {("a@example.com",), ("ops@example.com",)}


def test_build_test_email():
    subject, text, html_body = emailer.build_test(NOW, config())

    assert subject == "[ui-dashboard][TEST] SMTP alert delivery"
    assert "test email" in text
    assert "SMTP test" in html_body
