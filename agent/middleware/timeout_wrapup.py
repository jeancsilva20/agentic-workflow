from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, SystemMessage

_DEFAULT_TIMEOUT_SECONDS = 45 * 60
_DEFAULT_JIRA_TIMEOUT_SECONDS = 0  # 0 = disabled (no timeout for Jira runs by default)

_WRAPUP_INSTRUCTION = """
<time_limit_warning>
You have been running for a long time. Wrap up immediately: finish the current
step, save or report useful state, avoid starting new investigations, and end
your turn with the best available result.
</time_limit_warning>
"""

_JIRA_WRAPUP_INSTRUCTION = """
<time_limit_warning>
You have been running for a long time on this Jira task. Finish the current step,
then call `jira_park_at_gate` to park the card at the appropriate gate before ending.
Do not start new investigations. Save any partial work and post a comment summarising
progress so far.
</time_limit_warning>
"""


def _configured_timeout_seconds() -> int:
    raw = os.environ.get("OPEN_SWE_WRAPUP_TIMEOUT_SECONDS")
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS


def _configured_jira_timeout_seconds() -> int:
    """Return the Jira run wrapup timeout in seconds. 0 means disabled (no timeout)."""
    raw = os.environ.get("JIRA_RUN_WRAPUP_TIMEOUT_SECONDS")
    if not raw:
        return _DEFAULT_JIRA_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_JIRA_TIMEOUT_SECONDS
    return value if value >= 0 else _DEFAULT_JIRA_TIMEOUT_SECONDS


def _content_with_instruction(
    message: BaseMessage | None, instruction: str
) -> str | list[str | dict[Any, Any]]:
    if message is None:
        return instruction
    content = message.content
    if isinstance(content, list):
        return [*content, {"type": "text", "text": instruction}]
    return f"{content}\n\n{instruction}" if content else instruction


class TimeoutWrapupMiddleware(AgentMiddleware):
    def __init__(
        self,
        timeout_seconds: int | None = None,
        *,
        is_jira_run: bool = False,
    ) -> None:
        super().__init__()
        self._is_jira_run = is_jira_run
        if is_jira_run:
            if timeout_seconds is not None:
                # Explicit override: 0 means disabled, positive means active.
                self._timeout_seconds: int | None = timeout_seconds if timeout_seconds > 0 else None
            else:
                jira_t = _configured_jira_timeout_seconds()
                self._timeout_seconds = jira_t if jira_t > 0 else None
        else:
            self._timeout_seconds = timeout_seconds or _configured_timeout_seconds()
        # Graph construction should create one middleware instance per run; start
        # lazily so construction-time caching cannot age the run clock.
        self._start: float | None = None

    def _should_wrapup(self) -> bool:
        if self._timeout_seconds is None:
            return False
        if self._start is None:
            self._start = time.monotonic()
        return (time.monotonic() - self._start) >= self._timeout_seconds

    def _wrapup_instruction(self) -> str:
        return _JIRA_WRAPUP_INSTRUCTION if self._is_jira_run else _WRAPUP_INSTRUCTION

    def _apply(self, request: ModelRequest) -> ModelRequest:
        if not self._should_wrapup():
            return request
        content = _content_with_instruction(request.system_message, self._wrapup_instruction())
        return request.override(system_message=SystemMessage(content=content))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._apply(request))
