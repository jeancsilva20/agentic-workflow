"""Operational runtime configuration owned by the console (write side).

Two values an operator needs to change without a redeploy: shadow mode and the
poller's tick interval. Both were read once from an environment variable at
import time, so changing either meant restarting the LangGraph server.

Model and reasoning effort used to live here too, as a single global pair. They
do not any more: the model a run uses is decided per agent role by the router
(``agent.routing``), which no operator picks and no config file can override.

This module holds the values in memory, seeds them from those same environment
variables, and persists them to a small JSON file so a page refresh — or a
restart of either process — keeps what the operator selected. The poller reads
that same file (``agent.operational_config``), which is why the path comes from
there rather than being defined twice.

Never contains a secret: the two fields are the whole schema, and anything
else in a PUT is rejected rather than stored.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# The console is a standalone Flask app in a hyphenated directory, so it can't
# be a package — but the `agent/` package sits right next to it and owns the
# config file location. Importing it beats keeping a second copy in sync by
# hand.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.operational_config import (  # noqa: E402
    VALID_POLLING_INTERVAL_MINUTES,
    operational_config_path,
)

logger = logging.getLogger(__name__)

CONFIG_FIELDS: tuple[str, ...] = ("shadow_mode", "polling_interval_minutes")

_TRUTHY_ENV_VALUES = ("1", "true", "yes")


class ConfigValidationError(ValueError):
    """A rejected update: the message is safe to return to the caller."""


def available_polling_intervals() -> list[int]:
    return list(VALID_POLLING_INTERVAL_MINUTES)


def _env_shadow_mode() -> bool:
    return os.environ.get("JIRA_POLLER_SHADOW_MODE", "").strip().lower() in _TRUTHY_ENV_VALUES


def _env_polling_interval_minutes() -> int:
    """`JIRA_POLL_INTERVAL_SECONDS` mapped onto a selectable interval.

    The env var is free-form seconds while the API offers a fixed set of
    minutes, so an unlisted value snaps to the nearest one offered instead of
    presenting the operator with a value they could never pick again.
    """
    try:
        seconds = int(os.environ.get("JIRA_POLL_INTERVAL_SECONDS") or "60")
    except ValueError:
        seconds = 60
    minutes = max(1, seconds // 60)
    return min(VALID_POLLING_INTERVAL_MINUTES, key=lambda valid: (abs(valid - minutes), valid))


def _validate(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return the normalized config, or raise ``ConfigValidationError``."""
    shadow_mode = values.get("shadow_mode")
    if not isinstance(shadow_mode, bool):
        raise ConfigValidationError("shadow_mode must be a boolean")

    interval = values.get("polling_interval_minutes")
    if isinstance(interval, bool) or not isinstance(interval, int):
        raise ConfigValidationError("polling_interval_minutes must be an integer")
    if interval not in VALID_POLLING_INTERVAL_MINUTES:
        raise ConfigValidationError(
            "polling_interval_minutes must be one of "
            + ", ".join(str(v) for v in VALID_POLLING_INTERVAL_MINUTES)
        )

    return {
        "shadow_mode": shadow_mode,
        "polling_interval_minutes": interval,
    }


class OperationalConfig:
    """Thread-safe (Flask's dev server is multi-threaded) config with a JSON file behind it."""

    def __init__(self, path: str | Path | None = None) -> None:
        # Reentrant so a caller can hold the lock across `update()` *and* the
        # runtime side effects it triggers — see `transaction()`.
        self._lock = threading.RLock()
        self._path = Path(path) if path is not None else operational_config_path()
        self._values = self._load()
        self._file_stamp = self._current_file_stamp()

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Hold the config lock across an update and its runtime side effects.

        Persisting and applying have to be one atomic step. Two operators
        picking different polling intervals at the same moment would otherwise
        interleave — both PUTs report success, the file ends up on one value
        and the cron the other installed last on the other, with nothing to
        say which won.
        """
        with self._lock:
            yield

    # --- read ----------------------------------------------------------

    def get(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_if_file_changed()
            return dict(self._values)

    def options(self) -> dict[str, Any]:
        return {"available_polling_intervals": available_polling_intervals()}

    def reload(self) -> dict[str, Any]:
        """Re-read the file, discarding the in-memory copy (restart semantics)."""
        with self._lock:
            self._values = self._load()
            self._file_stamp = self._current_file_stamp()
            return dict(self._values)

    def _current_file_stamp(self) -> tuple[int, int] | None:
        try:
            stat = self._path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _refresh_if_file_changed(self) -> None:
        """Re-read the file when someone other than this object wrote it.

        The in-memory copy is an optimisation, not the truth: the file is what
        the poller reads. If they disagree — a second console process, an
        operator editing the file by hand — the API would otherwise report and
        diff against a value that stopped being real, and a PUT restoring the
        "current" value would look like a no-op and skip the runtime push.
        """
        stamp = self._current_file_stamp()
        if stamp != self._file_stamp:
            logger.info("Operational config file changed underneath us; re-reading %s", self._path)
            self._values = self._load()
            self._file_stamp = stamp

    # --- write ---------------------------------------------------------

    def update(
        self, partial: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[tuple[str, Any, Any]]]:
        """Validate, apply and persist a partial update.

        Returns the configuration now in effect plus the list of
        ``(field, old, new)`` that actually changed — the caller needs that to
        know which runtime side effects to fire and what to write to the log.
        """
        unknown = sorted(set(partial) - set(CONFIG_FIELDS))
        if unknown:
            raise ConfigValidationError(f"unknown config field(s): {', '.join(unknown)}")

        with self._lock:
            self._refresh_if_file_changed()
            validated = _validate({**self._values, **dict(partial)})
            changes = [
                (field, self._values[field], validated[field])
                for field in CONFIG_FIELDS
                if self._values[field] != validated[field]
            ]
            if changes:
                self._persist(validated)
            self._values = validated
            return dict(validated), changes

    # --- persistence ----------------------------------------------------

    def _defaults(self) -> dict[str, Any]:
        return {
            "shadow_mode": _env_shadow_mode(),
            "polling_interval_minutes": _env_polling_interval_minutes(),
        }

    def _load(self) -> dict[str, Any]:
        defaults = self._defaults()
        try:
            stored = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return defaults
        except (OSError, ValueError):
            logger.warning(
                "Ignoring unreadable operational config at %s; using environment defaults",
                self._path,
                exc_info=True,
            )
            return defaults
        if not isinstance(stored, dict):
            logger.warning("Ignoring operational config at %s: not a JSON object", self._path)
            return defaults

        overlay = {field: stored[field] for field in CONFIG_FIELDS if field in stored}
        try:
            return _validate({**defaults, **overlay})
        except ConfigValidationError as exc:
            # A hand-edited file, or a model that left the catalog since it was
            # written, must not brick the console — fall back loudly.
            logger.warning(
                "Operational config at %s is not usable (%s); using environment defaults",
                self._path,
                exc,
            )
            return defaults

    def _persist(self, values: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        # Write-then-rename: the poller reads this file on every tick and must
        # never see a half-written one.
        tmp_path.write_text(
            json.dumps(dict(values), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(tmp_path, self._path)
        self._file_stamp = self._current_file_stamp()


operational_config = OperationalConfig()
