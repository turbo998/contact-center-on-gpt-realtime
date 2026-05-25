"""smoke_whisper.py — issue #5

Connects to Azure Foundry's gpt-realtime-whisper deployment, streams one wav
file in, prints transcript deltas as they arrive, reports first-delta latency.

Usage:
    cd backend
    python -m scripts.smoke_whisper path/to/input.wav

Acceptance (from issue #5):
- 流式打印中文转写 delta
- 首字延迟 < 0.5s
- 终态字幕与音频内容一致

Env vars:
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_API_KEY    (dev) — or MI when APP_ENV=production
- AZURE_OPENAI_API_VERSION (default 2025-04-01-preview)
- DEPLOYMENT_WHISPER
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.realtime.sessions import WHISPER_SESSION  # noqa: E402
from scripts.smoke_translate import (  # noqa: E402
    SAMPLE_RATE,
    _make_client,
    _need_env,
    read_pcm16_wav,
)


async def run_smoke(input_wav: Path, chunk_ms: int = 100) -> dict:
    """Stream input_wav through whisper session, print deltas, return metrics."""
    pcm_in = read_pcm16_wav(input_wav)
    chunk_size = SAMPLE_RATE * 2 * chunk_ms // 1000

    deployment = _need_env("DEPLOYMENT_WHISPER")
    client = _make_client()

    t_send_start: float | None = None
    t_first_delta: float | None = None
    transcript_parts: list[str] = []

    async with client.beta.realtime.connect(model=deployment) as conn:  # pragma: no cover
        await conn.session.update(session=WHISPER_SESSION)

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

        async def receiver() -> None:
            nonlocal t_first_delta
            async for event in conn:
                etype = getattr(event, "type", "")
                # Whisper events come on the input_audio_transcription channel
                if etype == "conversation.item.input_audio_transcription.delta":
                    if t_first_delta is None:
                        t_first_delta = time.perf_counter()
                    delta = getattr(event, "delta", "")
                    transcript_parts.append(delta)
                    print(delta, end="", flush=True)
                elif etype == "conversation.item.input_audio_transcription.completed":
                    final = getattr(event, "transcript", "")
                    print()  # newline after streaming
                    print(f"[completed] {final}")
                    break
                elif etype == "error":
                    raise RuntimeError(f"Foundry error: {event}")

        await asyncio.gather(sender(), receiver())

    assert t_send_start is not None
    first_delta_ms = (
        (t_first_delta - t_send_start) * 1000 if t_first_delta else None
    )
    return {
        "first_delta_ms": first_delta_ms,
        "transcript": "".join(transcript_parts),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_wav", type=Path, help="Input wav (mono 16-bit @ 24kHz)")
    p.add_argument("--chunk-ms", type=int, default=100)
    args = p.parse_args(argv)

    if not args.input_wav.exists():
        print(f"ERROR: {args.input_wav} not found", file=sys.stderr)
        return 2

    result = asyncio.run(run_smoke(args.input_wav, args.chunk_ms))
    print("=" * 60)
    print(f"first_delta_ms : {result['first_delta_ms']:.0f}")
    print(f"transcript     : {result['transcript']!r}")
    if result["first_delta_ms"] is not None and result["first_delta_ms"] >= 500:
        print("WARN: first_delta_ms >= 500 — investigate (network? region?)")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
