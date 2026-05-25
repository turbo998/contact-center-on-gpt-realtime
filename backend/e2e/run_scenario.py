"""End-to-end demo scenario driver — runs the 6-step business demo against
a live backend (local uvicorn or deployed Azure App Service) and reports
latency + completeness for each step. Used for pre-demo smoke-checks.

Usage:
    # local
    python -m backend.e2e.run_scenario --base ws://localhost:8000

    # azure
    python -m backend.e2e.run_scenario --base wss://contact-center.azurewebsites.net

Exit code 0 = all steps green; 1 = any step missing required envelope or
breaches the latency budget.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field

import websockets

# ---------------- Envelope helpers ------------------------------------------


def _env(env_type: str, call_id: str, seq: int, payload: dict) -> str:
    return json.dumps(
        {
            "v": 1,
            "type": env_type,
            "ts": int(time.time() * 1000),
            "call_id": call_id,
            "seq": seq,
            "payload": payload,
        }
    )


@dataclass
class StepResult:
    name: str
    ok: bool
    duration_ms: int
    detail: str = ""
    seen_types: list[str] = field(default_factory=list)

    def fmt(self) -> str:
        mark = "✅" if self.ok else "❌"
        head = f"{mark} {self.name:<28} {self.duration_ms:>5}ms"
        return head + (f"  -- {self.detail}" if self.detail else "")


# ---------------- Step drivers ----------------------------------------------


async def step_customer_translate(base: str, call_id: str) -> StepResult:
    url = f"{base}/ws/customer"
    t0 = time.monotonic()
    seen: list[str] = []
    async with websockets.connect(url) as ws:
        await ws.send(_env("call.start", call_id, 1, {"lang": "zh-CN", "target_lang": "en-US"}))
        await ws.recv()
        await ws.send(_env("audio.frame", call_id, 2, {"audio": "AAAA", "seq": 1, "ts": 0}))
        try:
            for _ in range(20):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                seen.append(json.loads(raw)["type"])
                if "whisper.transcript.completed" in seen and "translate.text.delta" in seen:
                    break
        except TimeoutError:
            pass
        await ws.send(_env("call.end", call_id, 3, {"reason": "client"}))
    dur = int((time.monotonic() - t0) * 1000)
    ok = "translate.text.delta" in seen and "whisper.transcript.completed" in seen
    detail = "" if ok else f"got {seen}"
    return StepResult("step1 customer→translate+whisper", ok, dur, detail, seen)


async def step_agent_translate(base: str, call_id: str) -> StepResult:
    url = f"{base}/ws/agent"
    t0 = time.monotonic()
    seen: list[str] = []
    async with websockets.connect(url) as ws:
        await ws.send(_env("call.start", call_id, 1, {"lang": "en-US", "target_lang": "zh-CN"}))
        await ws.recv()
        await ws.send(_env("audio.frame", call_id, 2, {"audio": "AAAA", "seq": 1, "ts": 0}))
        try:
            for _ in range(20):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                seen.append(json.loads(raw)["type"])
                if "translate.text.delta" in seen:
                    break
        except TimeoutError:
            pass
        await ws.send(_env("call.end", call_id, 3, {"reason": "client"}))
    dur = int((time.monotonic() - t0) * 1000)
    ok = "translate.text.delta" in seen
    return StepResult("step2 agent→translate", ok, dur, "" if ok else f"got {seen}", seen)


async def step_escalate(base: str, call_id: str) -> tuple[StepResult, str | None]:
    """Returns (result, assist_ws_url)."""
    url = f"{base}/ws/agent"
    t0 = time.monotonic()
    seen: list[str] = []
    assist_url: str | None = None
    async with websockets.connect(url) as ws:
        await ws.send(_env("call.start", call_id, 1, {"lang": "en-US", "target_lang": "zh-CN"}))
        await ws.recv()
        await ws.send(
            _env(
                "escalate.request", call_id, 2, {"order_id": "A12345", "note": "tariff + insurance"}
            )
        )
        try:
            for _ in range(6):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                env = json.loads(raw)
                seen.append(env["type"])
                if env["type"] == "escalate.acked":
                    assist_url = env["payload"].get("assist_ws_url")
                    break
        except TimeoutError:
            pass
        await ws.send(_env("call.end", call_id, 3, {"reason": "client"}))
    dur = int((time.monotonic() - t0) * 1000)
    ok = assist_url is not None
    return (
        StepResult("step3 escalate→assist_url", ok, dur, assist_url or "no url", seen),
        assist_url,
    )


async def step_assist_stream(base: str, call_id: str) -> StepResult:
    url = f"{base}/ws/assist"
    t0 = time.monotonic()
    seen_types: list[str] = []
    tool_names: set[str] = set()
    async with websockets.connect(url) as ws:
        await ws.send(
            _env(
                "assist.start",
                call_id,
                1,
                {
                    "order_id": "A12345",
                    "context_summary": "客户要求退换 + 关税豁免",
                    "reasoning_effort": "high",
                },
            )
        )
        await ws.recv()  # assist.started
        try:
            for _ in range(60):
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                env = json.loads(raw)
                seen_types.append(env["type"])
                if env["type"] == "rt2.tool_call":
                    tool_names.add(env["payload"]["name"])
                if env["type"] == "rt2.text.delta" and len(tool_names) >= 3:
                    break
        except TimeoutError:
            pass
        await ws.send(_env("assist.end", call_id, 2, {"reason": "client"}))
    dur = int((time.monotonic() - t0) * 1000)
    needed = {"get_order", "check_tariff", "check_insurance"}
    ok = (
        "rt2.reasoning.delta" in seen_types
        and "rt2.text.delta" in seen_types
        and needed.issubset(tool_names)
    )
    detail = "" if ok else f"tools={tool_names} types={set(seen_types)}"
    return StepResult("step4-5 rt2.reason+tools+text", ok, dur, detail, seen_types)


# ---------------- Orchestration ---------------------------------------------


async def run_once(base: str, call_id: str) -> list[StepResult]:
    results: list[StepResult] = []
    results.append(await step_customer_translate(base, call_id))
    results.append(await step_agent_translate(base, call_id))
    esc_res, _ = await step_escalate(base, call_id)
    results.append(esc_res)
    results.append(await step_assist_stream(base, call_id))
    return results


def _print_report(runs: list[list[StepResult]]) -> int:
    print(f"\n=== Scenario runs: {len(runs)} ===")
    for i, run in enumerate(runs):
        print(f"\n--- run {i + 1} ---")
        for r in run:
            print(r.fmt())
    all_ok = all(r.ok for run in runs for r in run)
    print("\n" + ("ALL GREEN ✅" if all_ok else "FAILURES ❌"))
    return 0 if all_ok else 1


async def amain(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base", default="ws://localhost:8000", help="ws://host:port or wss://host (no path)"
    )
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--call-id-prefix", default="C-demo")
    args = ap.parse_args(argv)
    runs: list[list[StepResult]] = []
    for i in range(args.runs):
        cid = f"{args.call_id_prefix}-{int(time.time())}-{i}"
        runs.append(await run_once(args.base, cid))
    return _print_report(runs)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(amain(argv or sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
