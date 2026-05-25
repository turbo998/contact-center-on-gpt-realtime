/**
 * Pure DSP helpers for audio capture / playback.
 *
 * Extracted so the AudioWorklet logic is unit-testable without an
 * AudioWorkletGlobalScope (jsdom can't host a worklet).
 *
 * See docs/14-frontend-design.md §14.4 / §14.5.
 */

/** Linear-interpolation downsample of mono Float32 samples. */
export function downsampleFloat32(
  input: Float32Array,
  srcRate: number,
  dstRate: number,
): Float32Array {
  if (srcRate === dstRate) return input.slice();
  if (srcRate <= 0 || dstRate <= 0) {
    throw new Error("sample rates must be positive");
  }
  const ratio = srcRate / dstRate;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const srcPos = i * ratio;
    const idx = Math.floor(srcPos);
    const frac = srcPos - idx;
    const a = input[idx] ?? 0;
    const b = input[idx + 1] ?? a;
    out[i] = a + (b - a) * frac;
  }
  return out;
}

/** Convert Float32 (-1..1) samples to signed 16-bit PCM (little-endian). */
export function floatToPcm16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
  }
  return out;
}

/** Convert signed 16-bit PCM back to Float32 (-1..1). */
export function pcm16ToFloat32(input: Int16Array): Float32Array {
  const out = new Float32Array(input.length);
  for (let i = 0; i < input.length; i++) out[i] = input[i] / 0x8000;
  return out;
}

/**
 * Streaming framer — accumulates Float32 samples, emits fixed-size
 * Int16 PCM frames (e.g. 480 samples = 20ms @ 24kHz).
 *
 * Use one instance per source. Not thread-safe.
 */
export class PcmFramer {
  private buf: number[] = [];
  constructor(private readonly frameSamples: number) {
    if (frameSamples <= 0) throw new Error("frameSamples must be > 0");
  }

  /** Push samples, return zero or more complete frames as ArrayBuffers. */
  push(samples: Float32Array): ArrayBuffer[] {
    for (let i = 0; i < samples.length; i++) this.buf.push(samples[i]);
    const out: ArrayBuffer[] = [];
    while (this.buf.length >= this.frameSamples) {
      const chunk = this.buf.splice(0, this.frameSamples);
      const pcm = floatToPcm16(Float32Array.from(chunk));
      out.push(pcm.buffer);
    }
    return out;
  }

  /** Pending un-emitted samples (for tests). */
  get pending(): number {
    return this.buf.length;
  }

  reset(): void {
    this.buf = [];
  }
}
