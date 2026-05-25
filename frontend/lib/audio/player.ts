/**
 * Sequential PCM16 24 kHz player with jitter buffer.
 * Spec: docs/14-frontend-design.md §14.5.
 *
 * AudioContext is injected via factory for testability — production
 * code uses the real browser one, tests inject a fake.
 */
import { pcm16ToFloat32 } from "./pcm";

export interface PCMPlayerOpts {
  sampleRate?: number;
  jitterMs?: number;
  onUnderrun?: () => void;
  onPlayingChange?: (playing: boolean) => void;
  /** Test seam — defaults to `new AudioContext(...)`. */
  audioContextFactory?: (opts: { sampleRate: number }) => AudioContext;
}

export class PCMPlayer {
  readonly sampleRate: number;
  readonly jitterSec: number;
  private ctx: AudioContext;
  private nextStartTime = 0;
  private queueDepth = 0;
  private readonly factory: (opts: { sampleRate: number }) => AudioContext;
  private readonly opts: PCMPlayerOpts;

  constructor(opts: PCMPlayerOpts = {}) {
    this.opts = opts;
    this.sampleRate = opts.sampleRate ?? 24000;
    this.jitterSec = (opts.jitterMs ?? 100) / 1000;
    this.factory =
      opts.audioContextFactory ??
      (({ sampleRate }) => new AudioContext({ sampleRate }));
    this.ctx = this.factory({ sampleRate: this.sampleRate });
  }

  /** Push one PCM16 chunk; schedules playback on the AudioContext timeline. */
  enqueue(pcm16: ArrayBuffer): void {
    const i16 = new Int16Array(pcm16);
    if (i16.length === 0) return;
    const f32 = pcm16ToFloat32(i16);

    const buf = this.ctx.createBuffer(1, f32.length, this.sampleRate);
    buf.copyToChannel(f32, 0);

    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);

    const now = this.ctx.currentTime;
    const startAt = Math.max(this.nextStartTime, now + this.jitterSec);
    src.start(startAt);
    this.nextStartTime = startAt + buf.duration;

    const wasIdle = this.queueDepth === 0;
    this.queueDepth++;
    if (wasIdle) this.opts.onPlayingChange?.(true);
    src.onended = () => {
      this.queueDepth = Math.max(0, this.queueDepth - 1);
      if (this.queueDepth === 0) {
        this.opts.onPlayingChange?.(false);
        if (this.ctx.currentTime > this.nextStartTime) this.opts.onUnderrun?.();
      }
    };
  }

  /** Stop everything and rebuild the AudioContext. */
  reset(): void {
    this.nextStartTime = 0;
    this.queueDepth = 0;
    try {
      void this.ctx.close();
    } catch {
      /* ignore */
    }
    this.ctx = this.factory({ sampleRate: this.sampleRate });
  }

  async resume(): Promise<void> {
    await this.ctx.resume();
  }

  /** Expose for diagnostics / tests. */
  get queued(): number {
    return this.queueDepth;
  }
}
