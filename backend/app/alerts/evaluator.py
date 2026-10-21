"""Threshold evaluation and per-rule state.

State keys are ``"<rule_id>|<source>"``. ``last_fired_at``/``consecutive`` are
kept between cycles so a sustained breach produces one alert per cooldown and
a recovery email when it clears.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from .config import Rule

ALL_SOURCES = "all sources"


@dataclass
class RuleState:
    consecutive: int = 0
    firing: bool = False
    last_fired_at: dt.datetime | None = None
    last_value: int = 0

    def to_dict(self) -> dict:
        return {
            "consecutive": self.consecutive,
            "firing": self.firing,
            "last_fired_at": self.last_fired_at.isoformat(sep=" ")
            if self.last_fired_at else None,
            "last_value": self.last_value,
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "RuleState":
        last_fired = data.get("last_fired_at")
        return cls(
            consecutive=_to_int(data.get("consecutive")),
            firing=bool(data.get("firing", False)),
            last_fired_at=dt.datetime.fromisoformat(str(last_fired)) if last_fired else None,
            last_value=_to_int(data.get("last_value")),
        )


@dataclass(frozen=True)
class Trigger:
    rule: Rule
    source: str
    value: int
    threshold: int

    @property
    def key(self) -> str:
        return f"{self.rule.id}|{self.source}"


@dataclass(frozen=True)
class Recovery:
    rule: Rule
    source: str
    value: int
    threshold: int

    @property
    def key(self) -> str:
        return f"{self.rule.id}|{self.source}"


def _to_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _entries(rule: Rule, counts: pd.DataFrame | None) -> list[tuple[str, int]]:
    """(source label, value) pairs a rule should evaluate this cycle."""
    column = rule.column
    if counts is None or counts.empty or column not in counts.columns:
        if rule.source is None:
            return []
        label = ALL_SOURCES if rule.source == "*" else rule.source
        return [(label, 0)]

    if rule.source == "*":
        return [(ALL_SOURCES, _to_int(counts[column].fillna(0).sum()))]

    if rule.source is not None:
        if "SOURCE" not in counts.columns:
            return [(rule.source, 0)]
        match = counts[counts["SOURCE"].astype(str) == rule.source]
        value = _to_int(match[column].fillna(0).sum()) if not match.empty else 0
        return [(rule.source, value)]

    if "SOURCE" not in counts.columns:
        return []
    return [
        (str(row.get("SOURCE") or "unknown"), _to_int(row.get(column)))
        for _, row in counts.iterrows()
    ]


def evaluate(
    rules: tuple[Rule, ...] | list[Rule],
    counts_by_window: Mapping[int, pd.DataFrame],
    state: dict[str, RuleState],
    now: dt.datetime,
) -> tuple[list[Trigger], list[Recovery]]:
    """Compare the latest counts against every rule and mutate ``state``."""
    triggers: list[Trigger] = []
    recoveries: list[Recovery] = []
    seen_keys: set[str] = set()

    for rule in rules:
        if not rule.enabled:
            continue

        entries = _entries(rule, counts_by_window.get(rule.window_minutes))
        if not entries:
            # No data at all for a per-source rule: resolve whatever was firing.
            prefix = f"{rule.id}|"
            for key in [k for k in state if k.startswith(prefix)]:
                seen_keys.add(key)
                item = state[key]
                if item.firing:
                    recoveries.append(Recovery(
                        rule, key[len(prefix):], item.last_value, rule.threshold))
                    item.firing = False
                item.consecutive = 0
            continue

        for source, value in entries:
            key = f"{rule.id}|{source}"
            seen_keys.add(key)
            item = state.setdefault(key, RuleState())
            item.last_value = value

            if value > rule.threshold:
                item.consecutive += 1
                if item.consecutive < rule.breaches_required:
                    continue
                cooldown_elapsed = (
                    item.last_fired_at is None
                    or (now - item.last_fired_at) >= dt.timedelta(minutes=rule.cooldown_minutes)
                )
                if not item.firing or cooldown_elapsed:
                    triggers.append(Trigger(rule, source, value, rule.threshold))
                    item.firing = True
                    item.last_fired_at = now
            else:
                if item.firing:
                    recoveries.append(Recovery(rule, source, value, rule.threshold))
                    item.firing = False
                item.consecutive = 0

    for key in [k for k in state if k not in seen_keys]:
        del state[key]

    return triggers, recoveries
