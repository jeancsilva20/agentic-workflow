"""Fallback pricing for the models the router can pick.

LangSmith reports ``total_cost`` only for models it prices itself, and it
returns ``None`` — not zero — for the rest. This table is the fallback for that
case *only*: whenever LangSmith answers with a cost, that answer wins, because
it is the one billing agrees with.

Prices are per million tokens (USD), list price, no discounts. They are a copy
of a published table at a point in time, so every entry carries the date it was
copied: a stale price is a wrong invoice, and an undated one cannot be audited.
An unknown model returns ``None`` rather than a guess — a card with an
unpriceable run must read "unknown", never "$0.00".
"""

from __future__ import annotations

from dataclasses import dataclass

# Bump when any entry below changes.
PRICING_LAST_UPDATED = "2026-08-10"


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens for one model."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float
    updated: str

    def as_dict(self) -> dict[str, object]:
        return {
            "input_per_mtok": self.input_per_mtok,
            "output_per_mtok": self.output_per_mtok,
            "cache_read_per_mtok": self.cache_read_per_mtok,
            "updated": self.updated,
        }


# Exact catalog ids (``agent/dashboard/options.py``) first, so a version bump
# that changes a price does not silently inherit the family rate.
MODEL_PRICING: dict[str, ModelPrice] = {
    "anthropic:claude-haiku-4-5-20251001": ModelPrice(1.00, 5.00, 0.10, PRICING_LAST_UPDATED),
    "anthropic:claude-sonnet-5": ModelPrice(3.00, 15.00, 0.30, PRICING_LAST_UPDATED),
    "anthropic:claude-opus-5": ModelPrice(15.00, 75.00, 1.50, PRICING_LAST_UPDATED),
}

# The router names families, not versions (``router._model_for_family``), so a
# catalog version bump must not turn a priced run into an unpriced one. Family
# rates are the same list prices as above.
_FAMILY_PRICING: tuple[tuple[str, ModelPrice], ...] = (
    ("anthropic:claude-haiku", MODEL_PRICING["anthropic:claude-haiku-4-5-20251001"]),
    ("anthropic:claude-sonnet", MODEL_PRICING["anthropic:claude-sonnet-5"]),
    ("anthropic:claude-opus", MODEL_PRICING["anthropic:claude-opus-5"]),
)


def price_for(model_id: str | None) -> ModelPrice | None:
    """The price row for ``model_id``, by exact id then by family prefix."""
    if not model_id:
        return None
    exact = MODEL_PRICING.get(model_id)
    if exact is not None:
        return exact
    for prefix, price in _FAMILY_PRICING:
        if model_id.startswith(prefix):
            return price
    return None


def estimate_cost(
    model_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = None,
) -> float | None:
    """Estimated USD cost, or ``None`` when it cannot be computed.

    ``None`` when the model is not priced or no token counts are known — never
    ``0.0``, which would read as "this run was free".

    ``cache_read_tokens`` is the cached slice of ``input_tokens`` (LangSmith
    reports it under ``prompt_token_details``), billed at the much lower cache
    rate. Passing it is optional; leaving it out just prices every input token
    at the full rate, which overstates rather than understates.
    """
    price = price_for(model_id)
    if price is None:
        return None
    if input_tokens is None and output_tokens is None:
        return None

    prompt = max(int(input_tokens or 0), 0)
    completion = max(int(output_tokens or 0), 0)
    cached = min(max(int(cache_read_tokens or 0), 0), prompt)
    uncached = prompt - cached

    cost = (
        uncached * price.input_per_mtok
        + cached * price.cache_read_per_mtok
        + completion * price.output_per_mtok
    ) / 1_000_000
    return round(cost, 6)


def pricing_table() -> list[dict[str, object]]:
    """The whole table, for reporting what a cost estimate was based on."""
    return [{"model": model, **price.as_dict()} for model, price in sorted(MODEL_PRICING.items())]
