"""The deterministic complexity classifier behind every routing decision."""

from __future__ import annotations

import pytest

from agent.routing import (
    RISK_SIGNALS,
    ComplexityTier,
    active_risk_signals,
    classify_complexity,
    complexity_score,
)


def test_no_signals_is_low() -> None:
    """A task nobody said anything about is not automatically expensive."""
    assert classify_complexity(None) is ComplexityTier.LOW
    assert classify_complexity({}) is ComplexityTier.LOW
    assert complexity_score(None) == 0


@pytest.mark.parametrize(
    ("files_changed", "expected"),
    [
        (0, ComplexityTier.LOW),
        (3, ComplexityTier.LOW),
        (4, ComplexityTier.LOW),
        (10, ComplexityTier.MEDIUM),
        (19, ComplexityTier.MEDIUM),
        (20, ComplexityTier.MEDIUM),
        (500, ComplexityTier.MEDIUM),
    ],
)
def test_size_alone_never_reaches_high(files_changed: int, expected: ComplexityTier) -> None:
    """A wide but shallow change (a rename, a lint sweep) is not hard work."""
    assert classify_complexity({"files_changed": files_changed}) is expected


@pytest.mark.parametrize("signal", RISK_SIGNALS)
def test_one_risk_signal_reaches_high(signal: str) -> None:
    """Each risk area is on its own enough to justify a more careful model."""
    assert classify_complexity({signal: True}) is ComplexityTier.HIGH


def test_two_risk_signals_reach_critical() -> None:
    assert (
        classify_complexity({"has_migration": True, "has_auth_change": True})
        is ComplexityTier.CRITICAL
    )


def test_retries_raise_the_tier_on_their_own() -> None:
    """Coming back twice is evidence the work was harder than it looked."""
    assert classify_complexity({"retry_count": 1}) is ComplexityTier.LOW
    assert classify_complexity({"retry_count": 2}) is ComplexityTier.MEDIUM
    assert classify_complexity({"retry_count": 9}) is ComplexityTier.MEDIUM


def test_review_returns_count_alongside_retries() -> None:
    signals = {"retry_count": 2, "review_return_count": 2}
    assert complexity_score(signals) == 4
    assert classify_complexity(signals) is ComplexityTier.HIGH


def test_retry_and_review_points_are_capped() -> None:
    """A pathological loop must not drown out the signals that describe the work."""
    assert complexity_score({"retry_count": 50}) == 3
    assert complexity_score({"review_return_count": 50}) == 2


def test_signals_combine_into_critical() -> None:
    signals = {"files_changed": 25, "has_security": True, "retry_count": 1}
    assert complexity_score(signals) == 3 + 4 + 1
    assert classify_complexity(signals) is ComplexityTier.CRITICAL


def test_unknown_signals_are_ignored() -> None:
    assert classify_complexity({"has_emoji": True, "vibes": "bad"}) is ComplexityTier.LOW


@pytest.mark.parametrize("value", ["true", "yes", "1", 1, True])
def test_truthy_json_shapes_activate_a_signal(value: object) -> None:
    """Signals arrive from thread metadata, where booleans are often strings."""
    assert active_risk_signals({"has_migration": value}) == ("has_migration",)


@pytest.mark.parametrize("value", ["false", "no", "0", 0, False, None, "", "maybe"])
def test_falsy_or_junk_values_do_not_activate_a_signal(value: object) -> None:
    assert active_risk_signals({"has_migration": value}) == ()


@pytest.mark.parametrize("value", ["not-a-number", None, -5, [1, 2]])
def test_junk_counters_are_treated_as_absent(value: object) -> None:
    assert complexity_score({"files_changed": value, "retry_count": value}) == 0


def test_active_risk_signals_keeps_a_stable_order() -> None:
    """The reason string quotes this list, so its order must not depend on dict order."""
    signals = dict.fromkeys(reversed(RISK_SIGNALS), True)
    assert active_risk_signals(signals) == RISK_SIGNALS


def test_tiers_compare_by_severity_not_by_name() -> None:
    """The router does ``tier >= HIGH``; string ordering would sort CRITICAL first."""
    assert ComplexityTier.LOW < ComplexityTier.MEDIUM < ComplexityTier.HIGH
    assert ComplexityTier.HIGH < ComplexityTier.CRITICAL
    assert ComplexityTier.CRITICAL >= ComplexityTier.HIGH
    assert not ComplexityTier.LOW >= ComplexityTier.HIGH
