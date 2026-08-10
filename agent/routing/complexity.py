"""Deterministic complexity classification for a unit of agent work.

The router needs to know how hard a task is *before* the first model call, so
asking a model to judge it is circular — and it would spend a call, and
latency, on every routing decision. Instead the tier comes from signals the
workflow already knows: how much of the repository the change touches, whether
it crosses one of the areas where a wrong answer is expensive (auth,
migrations, security, concurrency), and how many times this work has already
come back.

The scoring is intentionally boring arithmetic: the same signals must always
produce the same tier, in a test, in a log line, and in production.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

# Signals that mean "getting this wrong is expensive", not "this is big".
# Each one alone is enough to lift a task to HIGH, which is what makes the
# router's escalation rule reachable without a large diff.
RISK_SIGNALS: tuple[str, ...] = (
    "has_migration",
    "has_auth_change",
    "has_security",
    "has_concurrency",
)

_RISK_SIGNAL_WEIGHT = 4

# Retries and review returns are evidence the cheap route already failed, but
# one of them is not by itself a hard task — hence a single point each, capped
# so a pathological loop can't drown out every other signal.
_MAX_RETRY_POINTS = 3
_MAX_REVIEW_RETURN_POINTS = 2

_FILE_COUNT_POINTS: tuple[tuple[int, int], ...] = ((20, 3), (10, 2), (4, 1))

_MEDIUM_THRESHOLD = 2
_HIGH_THRESHOLD = 4
_CRITICAL_THRESHOLD = 8


class ComplexityTier(Enum):
    """How hard the work is, ordered so ``tier >= ComplexityTier.HIGH`` reads plainly."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _TIER_RANKS[self]

    # ``Enum`` is unordered by default and the router compares tiers on every
    # decision; define the full set rather than inheriting string ordering,
    # which would put "critical" below "low".
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ComplexityTier):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: object) -> bool:
        if not isinstance(other, ComplexityTier):
            return NotImplemented
        return self.rank <= other.rank

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, ComplexityTier):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, ComplexityTier):
            return NotImplemented
        return self.rank >= other.rank

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


_TIER_RANKS: dict[ComplexityTier, int] = {
    ComplexityTier.LOW: 0,
    ComplexityTier.MEDIUM: 1,
    ComplexityTier.HIGH: 2,
    ComplexityTier.CRITICAL: 3,
}

DEFAULT_COMPLEXITY = ComplexityTier.MEDIUM


def _as_int(value: Any) -> int:
    """Signals arrive from thread metadata and JSON, so treat junk as absent."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y")
    return False


def active_risk_signals(signals: Mapping[str, Any] | None) -> tuple[str, ...]:
    """The risk signals set in ``signals``, in :data:`RISK_SIGNALS` order."""
    if not signals:
        return ()
    return tuple(name for name in RISK_SIGNALS if _as_bool(signals.get(name)))


def complexity_score(signals: Mapping[str, Any] | None) -> int:
    """The raw score behind :func:`classify_complexity` (exposed for logging/tests)."""
    if not signals:
        return 0

    score = 0
    files_changed = _as_int(signals.get("files_changed"))
    for threshold, points in _FILE_COUNT_POINTS:
        if files_changed >= threshold:
            score += points
            break

    score += _RISK_SIGNAL_WEIGHT * len(active_risk_signals(signals))
    score += min(_as_int(signals.get("retry_count")), _MAX_RETRY_POINTS)
    score += min(_as_int(signals.get("review_return_count")), _MAX_REVIEW_RETURN_POINTS)
    return score


def classify_complexity(signals: Mapping[str, Any] | None = None) -> ComplexityTier:
    """Map workflow signals onto a tier. No model call, no I/O, no clock."""
    score = complexity_score(signals)
    if score >= _CRITICAL_THRESHOLD:
        return ComplexityTier.CRITICAL
    if score >= _HIGH_THRESHOLD:
        return ComplexityTier.HIGH
    if score >= _MEDIUM_THRESHOLD:
        return ComplexityTier.MEDIUM
    return ComplexityTier.LOW
