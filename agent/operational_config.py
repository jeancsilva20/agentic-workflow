"""Read side of the operational runtime configuration (shadow mode, model,
effort, polling interval).

The agent console (``agent-console/config_store.py``) owns the write side and
is the source of truth; this module is how the poller — which runs in the
*other* process, the LangGraph server — reads what the operator selected.

The transport is a plain JSON file on the shared filesystem rather than an HTTP
call back to the console, so a console that is down, slow, or was never started
can never delay or break a tick: the file keeps the last applied value, and an
absent/unreadable file simply means "no override, use the environment default".
Nothing here ever reads or writes a secret — the file holds four operational
values and nothing else.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Kept next to the console that writes it. Overridable so a deployment that
# splits the two processes across filesystems (or a test) can point both sides
# at the same path.
_DEFAULT_PATH = (
    Path(__file__).resolve().parents[1] / "agent-console" / "data" / "operational_config.json"
)

VALID_POLLING_INTERVAL_MINUTES: tuple[int, ...] = (1, 5, 10, 30, 60)

# (path, mtime_ns, size) -> parsed contents. A tick only pays a stat() unless
# the console actually rewrote the file.
_cache: tuple[tuple[str, int, int], dict[str, Any]] | None = None


def operational_config_path() -> Path:
    override = os.environ.get("OPERATIONAL_CONFIG_PATH", "").strip()
    return Path(override) if override else _DEFAULT_PATH


def read_operational_config() -> dict[str, Any] | None:
    """The console-applied configuration, or ``None`` when there is none."""
    global _cache

    path = operational_config_path()
    try:
        stat = path.stat()
    except OSError:
        return None

    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _cache
    if cached is not None and cached[0] == key:
        return cached[1]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Ignoring unreadable operational config at %s", path, exc_info=True)
        return None
    if not isinstance(data, dict):
        logger.warning("Ignoring operational config at %s: not a JSON object", path)
        return None

    _cache = (key, data)
    return data


def shadow_mode_override() -> bool | None:
    """Console-selected shadow mode, or ``None`` to fall back to the env var."""
    config = read_operational_config()
    if config is None:
        return None
    value = config.get("shadow_mode")
    return value if isinstance(value, bool) else None


def lite_mode_override() -> bool | None:
    """Console-selected lite mode, or ``None`` when not set.

    When ``True``, the router forces Haiku on every agent role regardless of
    the normal routing table.  A ``None`` return means "no preference in the
    config file" — the router treats that the same as ``False``.
    """
    config = read_operational_config()
    if config is None:
        return None
    value = config.get("lite_mode")
    return value if isinstance(value, bool) else None


def polling_interval_minutes_override() -> int | None:
    """Console-selected polling interval, or ``None`` to fall back to the env var."""
    config = read_operational_config()
    if config is None:
        return None
    value = config.get("polling_interval_minutes")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value in VALID_POLLING_INTERVAL_MINUTES else None
