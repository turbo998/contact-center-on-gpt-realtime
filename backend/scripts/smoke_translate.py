"""smoke_translate.py — issue #4

Connects to Azure Foundry's gpt-realtime-translate deployment, streams one wav
file in, prints first-token latency, saves the translated audio out.

Usage:
    cd backend
    python -m scripts.smoke_translate path/to/input.wav --out out.wav

Acceptance (from issue #4):
- 读取一段中文 wav，调用 Foundry translate session
- 首字延迟 < 1s（实测打印）
- 终态译文音频可播放（保存为 wav），文本与音频内容对齐
- README 给出运行命令

Env vars (loaded from backend/.env if present):
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_API_KEY          (dev) — or use MI when APP_ENV=production
- AZURE_OPENAI_API_VERSION      (default 2025-04-01-preview)
- DEPLOYMENT_TRANSLATE
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import struct
import sys
import time
import wave
from pathlib import Path

# Allow running as `python -m scripts.smoke_translate` or `python smoke_translate.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.realtime.sessions import TRANSLATE_SESSION  # noqa: E402

SAMPLE_RATE = 24_000  # Realtime API pcm16 = 24kHz mono


# -------------------- wav helpers --------------------


def read_pcm16_wav(path: Path) -> bytes:
    """Read a wav file and return raw pcm16 mono @ 24kHz bytes.

    Raises if input isn't already 24kHz mono 16-bit (use ffmpeg/sox to convert).
    """
    with wave.open(str(path), "rb") as w:
        n_channels = w.getnchannels()
        sample_width = w.getsampwidth()
        framerate = w.getframerate()
        frames = w.readframes(w.getnframes())
    if n_channels != 1 or sample_width != 2 or framerate != SAMPLE_RATE:
        raise ValueError(
            f"{path}: need mono 16-bit @ {SAMPLE_RATE}Hz, got "
            f"channels={n_channels} width={sample_width} rate={framerate}. "
            f"Convert with: ffmpeg -i in.wav -ac 1 -ar 24000 -sample_fmt s16 out.wav"
        )
    return frames


def write_pcm16_wav(path: Path, pcm: bytes) -> None:
    """Write raw pcm16 mono @ 24kHz to a playable wav file."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)


def make_synthetic_pcm16(seconds: float = 1.0, freq: float = 440.0) -> bytes:
    """Generate a sine-wave pcm16 buffer (used by tests; no SciPy needed)."""
    import math

    n = int(seconds * SAMPLE_RATE)
    amp = 16000
    buf = bytearray()
    for i in range(n):
        v = int(amp * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        buf += struct.pack("<h", v)
    return bytes(buf)


# -------------------- Foundry client --------------------


def _need_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SystemExit(f"missing env var: {name}")
    return v


def _make_client():  # pragma: no cover — requires openai + azure-identity
    from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
    from openai import AsyncAzureOpenAI

    endpoint = _need_env("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    app_env = os.getenv("APP_ENV", "development")

    if app_env == "development" and os.getenv("AZURE_OPENAI_API_KEY"):
        return AsyncAzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=api_version,
            azure_endpoint=endpoint,
        )
    cred = DefaultAzureCredential()
    tp = get_bearer_token_provider(cred, "https://cognitiveservices.azure.com/.default")
    return AsyncAzureOpenAI(
        azure_ad_token_provider=tp,
        api_version=api_version,
        azure_endpoint=endpoint,
    )


# -------------------- main streaming logic --------------------


async def run_smoke(input_wav: Path, output_wav: Path, chunk_ms: int = 100) -> dict:
    """Stream input_wav through the translate session, save output, return metrics."""
    pcm_in = read_pcm16_wav(input_wav)
    chunk_size = SAMPLE_RATE * 2 * chunk_ms // 1000  # bytes

    deployment = _need_env("DEPLOYMENT_TRANSLATE")
    client = _make_client()

    t_audio_send_start: float | None = None
    t_first_audio_delta: float | None = None
    t_first_text_delta: float | None = None
    out_audio = bytearray()
    out_text_chunks: list[str] = []

    async with client.beta.realtime.connect(model=deployment) as conn:  # pragma: no cover
        await conn.session.update(session=TRANSLATE_SESSION)

        async def sender() -> None:
            nonlocal t_audio_send_start
            t_audio_send_start = time.perf_counter()
            for i in range(0, len(pcm_in), chunk_size):
                chunk = pcm_in[i : i + chunk_size]
                await conn.input_audio_buffer.append(
                    audio=base64.b64encode(chunk).decode("ascii")
                )
                await asyncio.sleep(chunk_ms / 1000)  # pace to real-time
            await conn.input_audio_buffer.commit()

        async def receiver() -> None:
            nonlocal t_first_audio_delta, t_first_text_delta
            async for event in conn:
                etype = getattr(event, "type", "")
                if etype == "response.audio.delta":
                    if t_first_audio_delta is None:
                        t_first_audio_delta = time.perf_counter()
                    out_audio.extend(base64.b64decode(event.delta))
                elif etype in ("response.text.delta", "response.audio_transcript.delta"):
                    if t_first_text_delta is None:
                        t_first_text_delta = time.perf_counter()
                    out_text_chunks.append(getattr(event, "delta", ""))
                elif etype == "response.done":
                    break
                elif etype == "error":
                    raise RuntimeError(f"Foundry error: {event}")

        await asyncio.gather(sender(), receiver())

    write_pcm16_wav(output_wav, bytes(out_audio))

    assert t_audio_send_start is not None
    first_audio_ms = (
        (t_first_audio_delta - t_audio_send_start) * 1000
        if t_first_audio_delta
        else None
    )
    first_text_ms = (
        (t_first_text_delta - t_audio_send_start) * 1000
        if t_first_text_delta
        else None
    )
    return {
        "first_audio_ms": first_audio_ms,
        "first_text_ms": first_text_ms,
        "out_text": "".join(out_text_chunks),
        "out_audio_bytes": len(out_audio),
        "out_audio_path": str(output_wav),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_wav", type=Path, help="Input wav (mono 16-bit @ 24kHz)")
    p.add_argument("--out", type=Path, default=Path("translate_out.wav"))
    p.add_argument("--chunk-ms", type=int, default=100)
    args = p.parse_args(argv)

    if not args.input_wav.exists():
        print(f"ERROR: {args.input_wav} not found", file=sys.stderr)
        return 2

    result = asyncio.run(run_smoke(args.input_wav, args.out, args.chunk_ms))
    print("=" * 60)
    print(f"first_audio_ms : {result['first_audio_ms']:.0f}")
    print(f"first_text_ms  : {result['first_text_ms']:.0f}")
    print(f"out_text       : {result['out_text']!r}")
    print(f"out_audio_bytes: {result['out_audio_bytes']}")
    print(f"out_audio_path : {result['out_audio_path']}")
    if result["first_audio_ms"] is not None and result["first_audio_ms"] >= 1000:
        print("WARN: first_audio_ms >= 1000 — investigate (network? region? model?)")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
