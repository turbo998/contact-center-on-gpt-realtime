import { describe, it, expect, vi } from "vitest";
import { PCMPlayer } from "./player";

/** Minimal AudioContext fake — just enough for PCMPlayer's surface. */
function makeFakeCtx() {
  const ended: Array<() => void> = [];
  const ctx = {
    currentTime: 0,
    sampleRate: 24000,
    destination: {} as AudioNode,
    createBuffer(_ch: number, length: number, sampleRate: number) {
      return {
        length,
        sampleRate,
        duration: length / sampleRate,
        copyToChannel: vi.fn(),
      } as unknown as AudioBuffer;
    },
    createBufferSource() {
      const src: Partial<AudioBufferSourceNode> & { onended?: () => void } = {
        buffer: null,
        connect: vi.fn(),
        start: vi.fn((when: number) => {
          // Schedule onended at `when + duration` — fire when ctx time passes it.
          ended.push(() => src.onended?.());
        }),
        onended: undefined,
      };
      return src as AudioBufferSourceNode;
    },
    resume: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
    /** Test helper: fire all pending onended callbacks. */
    _flush() {
      const cbs = ended.splice(0);
      cbs.forEach((cb) => cb());
    },
  };
  return ctx as unknown as AudioContext & { _flush: () => void };
}

describe("PCMPlayer", () => {
  it("schedules each enqueue and tracks queue depth", () => {
    const ctx = makeFakeCtx();
    const player = new PCMPlayer({ audioContextFactory: () => ctx });
    const buf = new Int16Array(2400).buffer; // 100ms @ 24k
    player.enqueue(buf);
    player.enqueue(buf);
    expect(player.queued).toBe(2);
  });

  it("ignores empty enqueues", () => {
    const ctx = makeFakeCtx();
    const player = new PCMPlayer({ audioContextFactory: () => ctx });
    player.enqueue(new Int16Array(0).buffer);
    expect(player.queued).toBe(0);
  });

  it("fires onPlayingChange(true) on first frame, (false) when drained", () => {
    const ctx = makeFakeCtx();
    const changes: boolean[] = [];
    const player = new PCMPlayer({
      audioContextFactory: () => ctx,
      onPlayingChange: (p) => changes.push(p),
    });
    player.enqueue(new Int16Array(2400).buffer);
    player.enqueue(new Int16Array(2400).buffer);
    expect(changes).toEqual([true]);
    ctx._flush();
    expect(changes).toEqual([true, false]);
    expect(player.queued).toBe(0);
  });

  it("reset clears queue and rebuilds the context", () => {
    let made = 0;
    const factory = () => {
      made++;
      return makeFakeCtx();
    };
    const player = new PCMPlayer({ audioContextFactory: factory });
    player.enqueue(new Int16Array(2400).buffer);
    player.reset();
    expect(player.queued).toBe(0);
    expect(made).toBe(2); // constructor + reset
  });
});
