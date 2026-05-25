"""Tests for backend/app/tools — fixture loader, three tools, dispatcher.

Coverage matrix (issue #7 §13.9 acceptance):
    - fixtures.json loads with 3/3/3 records.
    - get_order: A12345 happy, X99999 not_found, status field present.
    - check_tariff: CN-GB-COFFEE-MAKER happy, lowercase normalises, CN-FR not_found.
    - check_insurance: INS-7788 covers_tariff=True, INS-9999 not_found.
    - All tools sleep ≥ 100 ms (mock latency).
    - ToolDispatcher: dispatches happy, unknown_tool, invalid_json,
      invalid_arguments (TypeError), timeout, and always emits
      function_call_output + response.create pair.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest

from app.tools.dispatcher import ToolDispatcher
from app.tools.impl import (
    check_insurance,
    check_tariff,
    get_order,
    load_fixtures,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def test_fixtures_loads_three_orders_three_tariffs_three_insurances() -> None:
    fx = load_fixtures()
    assert set(fx.keys()) >= {"orders", "tariffs", "insurances"}
    assert len(fx["orders"]) >= 3
    assert len(fx["tariffs"]) >= 3
    assert len(fx["insurances"]) >= 3


# ---------------------------------------------------------------------------
# get_order
# ---------------------------------------------------------------------------


def test_get_order_a12345_returns_full_record() -> None:
    res = asyncio.run(get_order("A12345"))
    assert res["found"] is True
    assert res["sku"] == "COFFEE-MAKER"
    assert res["from_country"] == "CN"
    assert res["to_country"] == "GB"
    assert res["status"] == "delivered_damaged"
    assert res["insurance_policy_id"] == "INS-7788"


def test_get_order_x99999_returns_not_found() -> None:
    res = asyncio.run(get_order("X99999"))
    assert res["found"] is False
    assert res["reason"] == "not_found"
    assert res["query"] == {"order_id": "X99999"}


def test_get_order_simulates_100ms_latency() -> None:
    start = time.perf_counter()
    asyncio.run(get_order("A12345"))
    elapsed_ms = (time.perf_counter() - start) * 1000
    # docs/13.3 specifies 100–300 ms — allow generous lower bound (jitter)
    assert elapsed_ms >= 90, f"expected ≥90ms simulated latency, got {elapsed_ms:.1f}ms"


# ---------------------------------------------------------------------------
# check_tariff
# ---------------------------------------------------------------------------


def test_check_tariff_happy() -> None:
    res = asyncio.run(check_tariff("CN", "GB", "COFFEE-MAKER"))
    assert res["found"] is True
    assert res["rate_percent"] == 12.5
    assert res["amount"] == 18.50
    assert res["currency"] == "GBP"


def test_check_tariff_lowercase_input_normalises() -> None:
    res = asyncio.run(check_tariff("cn", "gb", "coffee-maker"))
    assert res["found"] is True
    assert res["from_country"] == "CN"


def test_check_tariff_unknown_route_not_found() -> None:
    res = asyncio.run(check_tariff("CN", "FR", "COFFEE-MAKER"))
    assert res["found"] is False
    assert res["reason"] == "not_found"
    assert res["query"]["to_country"] == "FR"


# ---------------------------------------------------------------------------
# check_insurance
# ---------------------------------------------------------------------------


def test_check_insurance_ins7788_full_coverage() -> None:
    res = asyncio.run(check_insurance("INS-7788"))
    assert res["found"] is True
    assert res["covers_tariff"] is True
    assert res["covers_shipping"] is True
    assert res["covers_replacement"] is True


def test_check_insurance_ins0001_basic_plan() -> None:
    res = asyncio.run(check_insurance("INS-0001"))
    assert res["found"] is True
    assert res["covers_tariff"] is False
    assert res["covers_shipping"] is False
    assert res["covers_replacement"] is True
    assert res["deductible"] == 30.00


def test_check_insurance_unknown_not_found() -> None:
    res = asyncio.run(check_insurance("INS-9999"))
    assert res["found"] is False
    assert res["reason"] == "not_found"


# ---------------------------------------------------------------------------
# ToolDispatcher
# ---------------------------------------------------------------------------


class _SendRecorder:
    """Captures events the dispatcher would send to rt-2."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, evt: dict[str, Any]) -> None:
        self.events.append(evt)


def _last_output(rec: _SendRecorder) -> dict[str, Any]:
    """Parse the output JSON from the last function_call_output event."""
    fco = [e for e in rec.events if e.get("item", {}).get("type") == "function_call_output"]
    assert fco, f"no function_call_output found in {rec.events}"
    return json.loads(fco[-1]["item"]["output"])


def test_dispatch_happy_emits_output_then_response_create() -> None:
    rec = _SendRecorder()
    dsp = ToolDispatcher(rec)
    asyncio.run(dsp.dispatch("get_order", "call_1", json.dumps({"order_id": "A12345"})))
    assert len(rec.events) == 2
    assert rec.events[0]["type"] == "conversation.item.create"
    assert rec.events[0]["item"]["call_id"] == "call_1"
    assert rec.events[1] == {"type": "response.create"}
    out = json.loads(rec.events[0]["item"]["output"])
    assert out["found"] is True
    assert out["sku"] == "COFFEE-MAKER"


def test_dispatch_unknown_tool_returns_structured_error() -> None:
    rec = _SendRecorder()
    dsp = ToolDispatcher(rec)
    asyncio.run(dsp.dispatch("nope", "call_2", "{}"))
    out = _last_output(rec)
    assert out == {"error": "unknown_tool", "name": "nope"}
    # Still followed by response.create so rt-2 can recover.
    assert rec.events[-1] == {"type": "response.create"}


def test_dispatch_invalid_json_returns_error() -> None:
    rec = _SendRecorder()
    dsp = ToolDispatcher(rec)
    asyncio.run(dsp.dispatch("get_order", "call_3", "{not json"))
    out = _last_output(rec)
    assert out["error"] == "invalid_json"


def test_dispatch_invalid_arguments_returns_error() -> None:
    rec = _SendRecorder()
    dsp = ToolDispatcher(rec)
    # get_order doesn't take 'wrong_field'
    asyncio.run(dsp.dispatch("get_order", "call_4", json.dumps({"wrong_field": "x"})))
    out = _last_output(rec)
    assert out["error"] == "invalid_arguments"


def test_dispatch_timeout_returns_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _SendRecorder()
    dsp = ToolDispatcher(rec)
    dsp.TIMEOUT_SECONDS = 0.05  # type: ignore[misc]

    async def slow(**_kw: Any) -> dict[str, Any]:
        await asyncio.sleep(1.0)
        return {"never": "returned"}

    dsp._registry["slow_tool"] = slow  # type: ignore[index]
    asyncio.run(dsp.dispatch("slow_tool", "call_5", "{}"))
    out = _last_output(rec)
    assert out["error"] == "timeout"
