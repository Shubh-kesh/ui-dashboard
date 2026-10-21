"""Threshold evaluation: consecutive breaches, cooldown, recovery, sources."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from app.alerts.config import Rule
from app.alerts.evaluator import ALL_SOURCES, RuleState, evaluate

NOW = dt.datetime(2026, 10, 21, 16, 0, 0)


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def blink_rule(**overrides) -> Rule:
    values = dict(
        id="blink", metric="blink_requests", source="S1",
        window_minutes=5, threshold=10, breaches_required=2,
        cooldown_minutes=15,
    )
    values.update(overrides)
    return Rule(**values)


def test_fires_after_consecutive_breaches_and_respects_cooldown():
    rule = blink_rule()
    state: dict[str, RuleState] = {}
    counts = {5: frame([{"SOURCE": "S1", "BLINK": 11}])}

    triggers, _ = evaluate([rule], counts, state, NOW)
    assert triggers == []
    assert state["blink|S1"].consecutive == 1

    triggers, _ = evaluate([rule], counts, state, NOW + dt.timedelta(minutes=1))
    assert len(triggers) == 1
    assert triggers[0].value == 11
    assert triggers[0].source == "S1"
    assert state["blink|S1"].firing is True

    # Still above, but inside the cooldown: no repeat.
    triggers, _ = evaluate([rule], counts, state, NOW + dt.timedelta(minutes=2))
    assert triggers == []

    # Cooldown elapsed: a reminder is sent.
    triggers, _ = evaluate([rule], counts, state, NOW + dt.timedelta(minutes=20))
    assert len(triggers) == 1


def test_resolves_when_value_drops_below_threshold():
    rule = blink_rule(breaches_required=1)
    state: dict[str, RuleState] = {}

    evaluate([rule], {5: frame([{"SOURCE": "S1", "BLINK": 11}])}, state, NOW)
    triggers, recoveries = evaluate(
        [rule], {5: frame([{"SOURCE": "S1", "BLINK": 10}])}, state,
        NOW + dt.timedelta(minutes=1))

    assert triggers == []
    assert len(recoveries) == 1
    assert recoveries[0].value == 10
    assert state["blink|S1"].firing is False
    assert state["blink|S1"].consecutive == 0


def test_star_aggregates_all_sources():
    rule = blink_rule(source="*", threshold=10, breaches_required=1)
    state: dict[str, RuleState] = {}

    triggers, _ = evaluate(
        [rule],
        {5: frame([
            {"SOURCE": "S1", "BLINK": 6},
            {"SOURCE": "S2", "BLINK": 5},
        ])},
        state, NOW,
    )

    assert len(triggers) == 1
    assert triggers[0].source == ALL_SOURCES
    assert triggers[0].value == 11


def test_omitted_source_evaluates_each_source_separately():
    rule = blink_rule(source=None, threshold=10, breaches_required=1)
    state: dict[str, RuleState] = {}

    triggers, _ = evaluate(
        [rule],
        {5: frame([
            {"SOURCE": "S1", "BLINK": 11},
            {"SOURCE": "S2", "BLINK": 5},
        ])},
        state, NOW,
    )

    assert [(t.source, t.value) for t in triggers] == [("S1", 11)]


def test_missing_data_resolves_per_source_rule():
    rule = blink_rule(source=None)
    state = {"blink|S1": RuleState(firing=True, last_value=12, consecutive=3)}

    triggers, recoveries = evaluate([rule], {5: frame([])}, state, NOW)

    assert triggers == []
    assert len(recoveries) == 1
    assert recoveries[0].source == "S1"
    assert state["blink|S1"].firing is False


def test_state_for_removed_rules_is_pruned():
    rule = blink_rule()
    state = {"old-rule|S1": RuleState(firing=True)}

    evaluate([rule], {5: frame([{"SOURCE": "S1", "BLINK": 1}])}, state, NOW)

    assert "old-rule|S1" not in state
    assert "blink|S1" in state


def test_disabled_rules_are_ignored():
    rule = blink_rule(enabled=False, threshold=0, breaches_required=1)
    state: dict[str, RuleState] = {}

    triggers, recoveries = evaluate(
        [rule], {5: frame([{"SOURCE": "S1", "BLINK": 99}])}, state, NOW)

    assert triggers == [] and recoveries == []
    assert state == {}
