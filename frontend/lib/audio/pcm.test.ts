import { describe, it, expect } from "vitest";
import {
  downsampleFloat32,
  floatToPcm16,
  pcm16ToFloat32,
  PcmFramer,
} from "./pcm";

describe("downsampleFloat32", () => {
  it("48k -> 24k halves the sample count (within 1)", () => {
    const input = new Float32Array(960); // 20ms @ 48k
    for (let i = 0; i < input.length; i++) input[i] = Math.sin(i / 10);
    const out = downsampleFloat32(input, 48000, 24000);
    expect(Math.abs(out.length - 480)).toBeLessThanOrEqual(1);
  });

  it("identity when src == dst rate", () => {
    const input = new Float32Array([0.1, -0.2, 0.3]);
    const out = downsampleFloat32(input, 24000, 24000);
    expect(out.length).toBe(3);
    for (let i = 0; i < 3; i++) {
      expect(out[i]).toBeCloseTo(input[i], 5);
    }
  });

  it("rejects non-positive sample rates", () => {
    expect(() => downsampleFloat32(new Float32Array(8), 0, 24000)).toThrow();
    expect(() => downsampleFloat32(new Float32Array(8), 48000, -1)).toThrow();
  });

  it("preserves low-frequency signal energy roughly (no silence)", () => {
    const input = new Float32Array(4800);
    for (let i = 0; i < input.length; i++) {
      input[i] = Math.sin((2 * Math.PI * 200 * i) / 48000);
    }
    const out = downsampleFloat32(input, 48000, 24000);
    const energy = out.reduce((s, x) => s + x * x, 0) / out.length;
    expect(energy).toBeGreaterThan(0.1);
  });
});

describe("floatToPcm16 / pcm16ToFloat32", () => {
  it("round-trips within quantization error", () => {
    const f = new Float32Array([0, 0.5, -0.5, 0.999, -0.999]);
    const back = pcm16ToFloat32(floatToPcm16(f));
    for (let i = 0; i < f.length; i++) {
      expect(Math.abs(back[i] - f[i])).toBeLessThan(0.001);
    }
  });

  it("clamps out-of-range floats to int16 bounds", () => {
    const f = new Float32Array([2, -2]);
    const p = floatToPcm16(f);
    expect(p[0]).toBe(0x7fff);
    expect(p[1]).toBe(-0x8000);
  });
});

describe("PcmFramer", () => {
  it("emits no frame until full frame is available", () => {
    const fr = new PcmFramer(480);
    expect(fr.push(new Float32Array(479))).toHaveLength(0);
    expect(fr.pending).toBe(479);
    const out = fr.push(new Float32Array(1));
    expect(out).toHaveLength(1);
    expect(out[0].byteLength).toBe(480 * 2); // PCM16
    expect(fr.pending).toBe(0);
  });

  it("emits multiple frames when input is larger", () => {
    const fr = new PcmFramer(480);
    const out = fr.push(new Float32Array(480 * 3 + 50));
    expect(out).toHaveLength(3);
    expect(fr.pending).toBe(50);
  });

  it("reset clears buffer", () => {
    const fr = new PcmFramer(480);
    fr.push(new Float32Array(100));
    fr.reset();
    expect(fr.pending).toBe(0);
  });

  it("rejects non-positive frame size", () => {
    expect(() => new PcmFramer(0)).toThrow();
  });
});
