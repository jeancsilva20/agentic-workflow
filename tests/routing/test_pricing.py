"""The fallback pricing table — used only when LangSmith reports no cost."""

from __future__ import annotations

from agent.routing.pricing import MODEL_PRICING, estimate_cost, price_for, pricing_table
from agent.routing.router import HAIKU_MODEL_ID, OPUS_MODEL_ID, SONNET_MODEL_ID


def test_every_routed_model_is_priced() -> None:
    """A model the router can pick but the table cannot price reports no cost."""
    for model_id in (HAIKU_MODEL_ID, SONNET_MODEL_ID, OPUS_MODEL_ID):
        assert price_for(model_id) is not None, model_id


def test_every_entry_is_dated() -> None:
    """An undated price cannot be audited against the published list."""
    for model, price in MODEL_PRICING.items():
        assert price.updated, model


def test_cost_is_per_million_tokens() -> None:
    price = price_for(SONNET_MODEL_ID)
    assert price is not None

    cost = estimate_cost(SONNET_MODEL_ID, 1_000_000, 1_000_000)

    assert cost == round(price.input_per_mtok + price.output_per_mtok, 6)


def test_opus_costs_more_than_haiku_for_the_same_work() -> None:
    opus = estimate_cost(OPUS_MODEL_ID, 10_000, 2_000)
    haiku = estimate_cost(HAIKU_MODEL_ID, 10_000, 2_000)
    assert opus is not None and haiku is not None

    assert opus > haiku


def test_cached_input_is_billed_at_the_cache_rate() -> None:
    price = price_for(SONNET_MODEL_ID)
    assert price is not None

    full = estimate_cost(SONNET_MODEL_ID, 1_000_000, 0)
    cached = estimate_cost(SONNET_MODEL_ID, 1_000_000, 0, 1_000_000)
    assert full is not None and cached is not None

    assert cached == round(price.cache_read_per_mtok, 6)
    assert cached < full


def test_cache_read_larger_than_input_does_not_go_negative() -> None:
    cost = estimate_cost(SONNET_MODEL_ID, 100, 0, 10_000)

    assert cost is not None and cost >= 0


def test_a_version_bump_still_prices_through_the_family() -> None:
    """The router names families; a catalog version bump must not unprice a run."""
    assert estimate_cost("anthropic:claude-sonnet-9-20990101", 1_000, 1_000) is not None


def test_unknown_model_has_no_cost_rather_than_a_free_one() -> None:
    assert estimate_cost("some-provider:mystery-model", 10_000, 5_000) is None


def test_no_token_counts_means_no_cost() -> None:
    assert estimate_cost(SONNET_MODEL_ID, None, None) is None


def test_zero_tokens_is_a_real_zero() -> None:
    """Distinct from unknown: a run that used nothing did cost nothing."""
    assert estimate_cost(SONNET_MODEL_ID, 0, 0) == 0.0


def test_pricing_table_reports_what_an_estimate_was_based_on() -> None:
    rows = pricing_table()

    assert rows
    for row in rows:
        assert {"model", "input_per_mtok", "output_per_mtok", "cache_read_per_mtok", "updated"} <= (
            set(row)
        )
