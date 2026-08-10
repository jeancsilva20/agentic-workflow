"""What each model can actually be asked for, derived from the model catalog.

The router picks an effort per role, but effort is not a universal knob: each
model advertises its own list in ``agent/dashboard/options.py`` and rejects
anything outside it at request time (Kimi K3 refuses ``medium``, GLM only
takes ``none``/``high``/``max``). Deriving the registry from that catalog
instead of restating it here means a model whose efforts change in one place
cannot start failing requests from the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..dashboard.options import SUPPORTED_MODELS


@dataclass(frozen=True)
class ModelCapability:
    """The effort facts about one model the router needs before routing to it."""

    model_id: str
    efforts: tuple[str, ...]
    default_effort: str | None

    @property
    def supports_effort(self) -> bool:
        return bool(self.efforts)

    def accepts(self, effort: str | None) -> bool:
        return effort is not None and effort in self.efforts


@lru_cache(maxsize=1)
def _registry() -> dict[str, ModelCapability]:
    return {
        model["id"]: ModelCapability(
            model_id=model["id"],
            efforts=tuple(model["efforts"]),
            default_effort=model.get("default_effort") or None,
        )
        for model in SUPPORTED_MODELS
    }


def model_capability(model_id: str) -> ModelCapability | None:
    """The capability record for ``model_id``, or ``None`` if it left the catalog."""
    return _registry().get(model_id)


def supports_effort(model_id: str, effort: str | None = None) -> bool:
    """Whether ``model_id`` takes an effort at all, or a specific one when given."""
    capability = model_capability(model_id)
    if capability is None:
        return False
    if effort is None:
        return capability.supports_effort
    return capability.accepts(effort)


def safe_effort_for(model_id: str, effort: str | None) -> str | None:
    """The effort safe to send to ``model_id``, or ``None``.

    ``None`` means "send no effort at all" — either the caller asked for none,
    the model takes none, or the requested level is not one this model
    advertises. Never substitutes a different level: a role that asked for
    ``high`` and silently got ``low`` would be a routing decision nobody made.
    """
    if effort is None:
        return None
    return effort if supports_effort(model_id, effort) else None
