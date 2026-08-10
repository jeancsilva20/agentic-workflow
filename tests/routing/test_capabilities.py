"""The effort registry that keeps the router from sending a rejected parameter."""

from __future__ import annotations

import pytest

from agent.dashboard.options import SUPPORTED_MODELS
from agent.routing import (
    HAIKU_MODEL_ID,
    OPUS_MODEL_ID,
    SONNET_MODEL_ID,
    model_capability,
    safe_effort_for,
    supports_effort,
)

_KIMI = "fireworks:accounts/fireworks/models/kimi-k3"  # efforts: low/high/max only


def test_registry_covers_every_catalog_model() -> None:
    """One source of truth: a model added to the catalog is routable at once."""
    for model in SUPPORTED_MODELS:
        capability = model_capability(model["id"])
        assert capability is not None
        assert capability.efforts == tuple(model["efforts"])


@pytest.mark.parametrize("model_id", [HAIKU_MODEL_ID, SONNET_MODEL_ID, OPUS_MODEL_ID])
def test_routed_models_are_in_the_catalog(model_id: str) -> None:
    assert model_capability(model_id) is not None


def test_a_model_outside_the_catalog_has_no_capability() -> None:
    assert model_capability("anthropic:claude-imaginary-9") is None
    assert supports_effort("anthropic:claude-imaginary-9") is False
    assert safe_effort_for("anthropic:claude-imaginary-9", "high") is None


def test_supports_effort_answers_both_questions() -> None:
    assert supports_effort(_KIMI) is True  # takes an effort at all
    assert supports_effort(_KIMI, "high") is True  # takes this one
    assert supports_effort(_KIMI, "medium") is False  # not this one


def test_unsupported_effort_is_dropped_not_substituted() -> None:
    """Silently downgrading "high" to whatever the model takes is a decision nobody made."""
    assert safe_effort_for(_KIMI, "medium") is None
    assert safe_effort_for(_KIMI, "max") == "max"


def test_no_effort_requested_stays_none() -> None:
    assert safe_effort_for(SONNET_MODEL_ID, None) is None
