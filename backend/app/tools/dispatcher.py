"""Tool dispatcher — glues rt-2 function calls to local async tool impls.

Spec: docs/13-mock-data-and-tools.md §13.6.

Wire-up::

    rt-2 → response.function_call_arguments.done(name, call_id, arguments_json)
         ↓
    ToolDispatcher.dispatch(name, call_id, arguments_json)
         ↓
    rt-2 ← conversation.item.create(type=function_call_output, call_id, output)
    rt-2 ← response.create   # nudge rt-2 to continue reasoning
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.tools.impl import check_insurance, check_tariff, get_order

log = logging.getLogger(__name__)

ToolFn = Callable[..., Awaitable[dict[str, Any]]]


class ToolDispatcher:
    """Dispatch rt-2 function calls to local async implementations.

    All branches (happy, unknown_tool, invalid_json, invalid_arguments,
    timeout, internal) end with `function_call_output + response.create`
    so rt-2 can recover gracefully (docs/13.6 key design points).
    """

    TIMEOUT_SECONDS: float = 5.0

    def __init__(self, send_to_rt2: Callable[[dict[str, Any]], Awaitable[None]]):
        self._send = send_to_rt2
        self._registry: dict[str, ToolFn] = {
            "get_order": get_order,
            "check_tariff": check_tariff,
            "check_insurance": check_insurance,
        }

    async def dispatch(self, name: str, call_id: str, arguments_json: str) -> None:
        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            await self._reply(call_id, {"error": "invalid_json", "detail": str(exc)})
            return

        fn = self._registry.get(name)
        if fn is None:
            await self._reply(call_id, {"error": "unknown_tool", "name": name})
            return

        log.info("tool.dispatch", extra={"tool": name, "call_id": call_id, "args": args})

        try:
            result = await asyncio.wait_for(fn(**args), timeout=self.TIMEOUT_SECONDS)
        except TimeoutError:
            await self._reply(call_id, {"error": "timeout", "limit_s": self.TIMEOUT_SECONDS})
            return
        except TypeError as exc:  # bad arg shape
            await self._reply(call_id, {"error": "invalid_arguments", "detail": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("tool.failed", extra={"tool": name})
            await self._reply(call_id, {"error": "internal", "detail": repr(exc)})
            return

        await self._reply(call_id, result)

    async def _reply(self, call_id: str, output: dict[str, Any]) -> None:
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output, ensure_ascii=False),
                },
            }
        )
        # Per Realtime API: function_call_output does not auto-trigger
        # the next response — caller must `response.create` explicitly.
        await self._send({"type": "response.create"})
