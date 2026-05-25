"""smoke_rt2.py — issue #6

Validates the Azure Foundry `gpt-realtime-2` deployment for reasoning + tool
calls.

Streams one wav question into an assistant session (with the three escalate
tools registered), prints reasoning trace, captures function_call deltas,
locally dispatches via ToolDispatcher, feeds results back, prints final audio
duration + reasoning summary + per-stage latency.

Usage:
    cd backend
    python -m scripts.smoke_rt2 path/to/question.wav \\
        --out rt2_out.wav --reasoning-effort medium --order-id A12345

Acceptance (from issue #6):
- 发送一句音频问题 + system prompt（含 get_order 工具）
- 首音延迟 < 2s (reasoning.effort=medium)
- 推理 trace 非空
- 若 prompt 触发工具，能看到 `response.function_call_arguments.delta` 流

Env vars (loaded from backend/.env if present):
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_API_KEY          (dev) — or use MI when APP_ENV=production
- AZURE_OPENAI_API_VERSION      (default 2025-04-01-preview)
- DEPLOYMENT_RT2
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import sys
import time
from pathlib import Path
from typing import Any

# Allow running as `python -m scripts.smoke_rt2` or `python smoke_rt2.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.realtime.sessions import ASSISTANT_SESSION  # noqa: E402
from app.tools.dispatcher import ToolDispatcher  # noqa: E402
from scripts.smoke_translate import (  # noqa: E402
    SAMPLE_RATE,
    _make_client,
    _need_env,
    read_pcm16_wav,
    write_pcm16_wav,
)


def build_session(reasoning_effort: str, order_hint: str | None) -> dict[str, Any]:
    """Clone ASSISTANT_SESSION and override reasoning.effort + add hint."""
    s = copy.deepcopy(ASSISTANT_SESSION)
    s["reasoning"] = {"effort": reasoning_effort}
    if order_hint:
        # Append a hint so the model is encouraged to call get_order — the
        # acceptance criterion requires we *see* function_call deltas stream.
        s["instructions"] = (
            s["instructions"]
            + f"\n\n本次上下文的订单号：{order_hint}。请先调用 get_order 工具确认订单详情，"
            f"再给出方案。"
        )
    return s


async def run_smoke(  # pragma: no cover — live Foundry streaming
    input_wav: Path,
    output_wav: Path,
    reasoning_effort: str = "medium",
    order_hint: str | None = "A12345",
    chunk_ms: int = 100,
) -> dict[str, Any]:
    """Stream input_wav through rt-2 + dispatch tools + collect metrics."""
    pcm_in = read_pcm16_wav(input_wav)
    chunk_size = SAMPLE_RATE * 2 * chunk_ms // 1000

    deployment = _need_env("DEPLOYMENT_RT2")
    session_cfg = build_session(reasoning_effort, order_hint)
    client = _make_client()

    t_send_start: float | None = None
    t_first_audio: float | None = None
    t_first_reasoning: float | None = None
    out_audio = bytearray()
    reasoning_chunks: list[str] = []
    function_calls: list[dict[str, Any]] = []  # {call_id, name, args_buf}
    fc_index: dict[str, dict[str, Any]] = {}

    async with client.beta.realtime.connect(model=deployment) as conn:
        await conn.session.update(session=session_cfg)

        # Wire dispatcher to send back over the same connection.
        async def _send_evt(evt: dict[str, Any]) -> None:
            # The SDK's `conn.send(...)` accepts a dict envelope.
            await conn.send(evt)

        dispatcher = ToolDispatcher(_send_evt)

        async def sender() -> None:
            nonlocal t_send_start
            t_send_start = time.perf_counter()
            for i in range(0, len(pcm_in), chunk_size):
                chunk = pcm_in[i : i + chunk_size]
                await conn.input_audio_buffer.append(
                    audio=base64.b64encode(chunk).decode("ascii")
                )
                await asyncio.sleep(chunk_ms / 1000)
            await conn.input_audio_buffer.commit()
            await conn.response.create()

        async def receiver() -> None:
            nonlocal t_first_audio, t_first_reasoning
            async for event in conn:
                etype = getattr(event, "type", "")

                if etype == "response.audio.delta":
                    if t_first_audio is None:
                        t_first_audio = time.perf_counter()
                    out_audio.extend(base64.b64decode(event.delta))

                elif etype in ("response.reasoning.delta", "response.reasoning_text.delta"):
                    if t_first_reasoning is None:
                        t_first_reasoning = time.perf_counter()
                    delta = getattr(event, "delta", "")
                    reasoning_chunks.append(delta)
                    print(f"[reasoning] {delta}", end="", flush=True)

                elif etype == "response.function_call_arguments.delta":
                    call_id = getattr(event, "call_id", "?")
                    delta = getattr(event, "delta", "")
                    entry = fc_index.setdefault(
                        call_id,
                        {"call_id": call_id, "name": getattr(event, "name", ""), "args_buf": ""},
                    )
                    entry["args_buf"] += delta
                    print(f"[fc.delta {call_id}] {delta}", flush=True)

                elif etype == "response.function_call_arguments.done":
                    call_id = getattr(event, "call_id", "?")
                    name = getattr(event, "name", "")
                    arguments = getattr(event, "arguments", "{}")
                    entry = fc_index.get(call_id, {"call_id": call_id, "name": name, "args_buf": arguments})
                    entry["name"] = name
                    entry["arguments"] = arguments
                    function_calls.append(entry)
                    print(f"\n[fc.done] {name}({arguments}) — dispatching", flush=True)
                    await dispatcher.dispatch(name, call_id, arguments)

                elif etype == "response.done":
                    break

                elif etype == "error":
                    raise RuntimeError(f"Foundry error: {event}")

        await asyncio.gather(sender(), receiver())

    write_pcm16_wav(output_wav, bytes(out_audio))

    assert t_send_start is not None
    first_audio_ms = (
        (t_first_audio - t_send_start) * 1000 if t_first_audio else None
    )
    first_reasoning_ms = (
        (t_first_reasoning - t_send_start) * 1000 if t_first_reasoning else None
    )
    return {
        "first_audio_ms": first_audio_ms,
        "first_reasoning_ms": first_reasoning_ms,
        "reasoning_trace": "".join(reasoning_chunks),
        "function_calls": function_calls,
        "out_audio_bytes": len(out_audio),
        "out_audio_path": str(output_wav),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_wav", type=Path)
    p.add_argument("--out", type=Path, default=Path("rt2_out.wav"))
    p.add_argument(
        "--reasoning-effort",
        choices=["minimal", "low", "medium", "high"],
        default="medium",
    )
    p.add_argument("--order-id", default="A12345", help="Order hint injected into prompt")
    p.add_argument("--chunk-ms", type=int, default=100)
    args = p.parse_args(argv)

    if not args.input_wav.exists():
        print(f"ERROR: {args.input_wav} not found", file=sys.stderr)
        return 2

    result = asyncio.run(  # pragma: no cover
        run_smoke(
            args.input_wav,
            args.out,
            reasoning_effort=args.reasoning_effort,
            order_hint=args.order_id,
            chunk_ms=args.chunk_ms,
        )
    )
    print("\n" + "=" * 60)
    fa = result["first_audio_ms"]
    fr = result["first_reasoning_ms"]
    print(f"first_audio_ms     : {fa:.0f}" if fa else "first_audio_ms     : (none)")
    print(f"first_reasoning_ms : {fr:.0f}" if fr else "first_reasoning_ms : (none)")
    print(f"reasoning_chars    : {len(result['reasoning_trace'])}")
    print(f"function_calls     : {len(result['function_calls'])}")
    for fc in result["function_calls"]:
        print(f"  - {fc['name']}({fc.get('arguments', fc.get('args_buf', ''))})")
    print(f"out_audio_bytes    : {result['out_audio_bytes']}")
    print(f"out_audio_path     : {result['out_audio_path']}")

    # Acceptance (issue #6): first audio < 2s on reasoning.effort=medium
    if fa is None or fa >= 2000:
        print(
            "WARN: first_audio_ms >= 2000 — investigate "
            "(network? region? reasoning effort?)"
        )
        return 1
    if not result["reasoning_trace"]:
        print("WARN: empty reasoning trace — rt-2 may not be a reasoning deployment")
        return 1
    if args.order_id and not result["function_calls"]:
        print("WARN: no function_call observed — model didn't invoke get_order")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
