"""Mock implementations of the three escalate-flow CRM tools.

Spec: docs/13-mock-data-and-tools.md §13.3–13.5.

All three tools:
- Read from `fixtures.json` (loaded lazily once per process).
- Simulate 100–300 ms of network latency via `asyncio.sleep`.
- Return either a `*Found` TypedDict (with `found=True`) or a `NotFound`
  envelope shaped `{"found": False, "reason": "not_found", "query": {...}}`.

The dispatcher (`app.tools.dispatcher`) wraps these into Realtime API
`function_call_output` events; see docs/13.6.
"""
from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any, Literal, TypedDict

_FIXTURES_PATH = Path(__file__).with_name("fixtures.json")
_FIXTURES: dict[str, Any] | None = None


def load_fixtures() -> dict[str, Any]:
    """Load fixtures.json once; cached at module scope.

    Fail-fast on missing file (per docs/13.3 error table).
    """
    global _FIXTURES
    if _FIXTURES is None:
        with _FIXTURES_PATH.open("r", encoding="utf-8") as f:
            _FIXTURES = json.load(f)
    return _FIXTURES


async def _sleep_jitter() -> None:
    """Simulate 100–300 ms CRM latency for realistic rt-2 reasoning timeline."""
    await asyncio.sleep(random.uniform(0.1, 0.3))


# ---------------------------------------------------------------------------
# Shared envelope
# ---------------------------------------------------------------------------


class NotFound(TypedDict):
    found: Literal[False]
    reason: Literal["not_found"]
    query: dict[str, Any]


# ---------------------------------------------------------------------------
# get_order (docs/13.3)
# ---------------------------------------------------------------------------


class OrderFound(TypedDict):
    found: Literal[True]
    order_id: str
    sku: str
    product_name: str
    from_country: str
    to_country: str
    status: str
    amount: float
    currency: str
    ordered_at: str
    delivered_at: str | None
    customer_id: str
    insurance_policy_id: str | None
    notes: str | None


OrderResult = OrderFound | NotFound


async def get_order(order_id: str) -> OrderResult:
    await _sleep_jitter()
    rec = load_fixtures()["orders"].get(order_id)
    if rec is None:
        return {"found": False, "reason": "not_found", "query": {"order_id": order_id}}
    return {"found": True, **rec}  # type: ignore[typeddict-item]


# ---------------------------------------------------------------------------
# check_tariff (docs/13.4)
# ---------------------------------------------------------------------------


class TariffFound(TypedDict):
    found: Literal[True]
    from_country: str
    to_country: str
    sku: str
    rate_percent: float
    amount: float
    currency: str
    basis: str


TariffResult = TariffFound | NotFound


async def check_tariff(from_country: str, to_country: str, sku: str) -> TariffResult:
    await _sleep_jitter()
    key = f"{from_country.upper()}-{to_country.upper()}-{sku.upper()}"
    rec = load_fixtures()["tariffs"].get(key)
    if rec is None:
        return {
            "found": False,
            "reason": "not_found",
            "query": {
                "from_country": from_country.upper(),
                "to_country": to_country.upper(),
                "sku": sku.upper(),
            },
        }
    return {"found": True, **rec}  # type: ignore[typeddict-item]


# ---------------------------------------------------------------------------
# check_insurance (docs/13.5)
# ---------------------------------------------------------------------------


class InsuranceFound(TypedDict):
    found: Literal[True]
    policy_id: str
    customer_id: str
    covers_shipping: bool
    covers_tariff: bool
    covers_replacement: bool
    deductible: float
    currency: str
    valid_until: str
    notes: str | None


InsuranceResult = InsuranceFound | NotFound


async def check_insurance(policy_id: str) -> InsuranceResult:
    await _sleep_jitter()
    rec = load_fixtures()["insurances"].get(policy_id)
    if rec is None:
        return {"found": False, "reason": "not_found", "query": {"policy_id": policy_id}}
    return {"found": True, **rec}  # type: ignore[typeddict-item]
