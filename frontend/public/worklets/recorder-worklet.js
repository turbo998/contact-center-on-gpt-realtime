/* eslint-disable */
// AudioWorkletProcessor — runs in AudioWorkletGlobalScope.
// In: browser AudioContext rate (typically 48000Hz, mono).
// Out: 24kHz PCM16 frames, 480 samples = 20ms = 960 bytes each.
//
// Plain JS (no TypeScript) so Next.js serves it untouched from /public.

class RecorderProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() { return []; }

  constructor() {
    super();
    this.TARGET_RATE = 24000;
    this.FRAME_SAMPLES = 480;
    this.ratio = sampleRate / this.TARGET_RATE; // global `sampleRate`
    this.resampleBuf = [];
    this.srcCursor = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;

    for (; this.srcCursor < input.length; this.srcCursor += this.ratio) {
      const i = Math.floor(this.srcCursor);
      const frac = this.srcCursor - i;
      const a = input[i] || 0;
      const b = input[i + 1] !== undefined ? input[i + 1] : a;
      this.resampleBuf.push(a + (b - a) * frac);
    }
    this.srcCursor -= input.length;

    while (this.resampleBuf.length >= this.FRAME_SAMPLES) {
      const chunk = this.resampleBuf.splice(0, this.FRAME_SAMPLES);
      const pcm16 = new Int16Array(this.FRAME_SAMPLES);
      for (let i = 0; i < this.FRAME_SAMPLES; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
    return true;
  }
}

registerProcessor("recorder-processor", RecorderProcessor);
