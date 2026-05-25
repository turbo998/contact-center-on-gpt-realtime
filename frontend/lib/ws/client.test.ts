import { describe, it, expect, vi } from "vitest";
import { createWsClient } from "./client";

/** Minimal fake WebSocket controllable in tests. */
class FakeWs {
  static OPEN = 1;
  binaryType = "";
  readyState = 0;
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;
  sent: unknown[] = [];
  closeCalls = 0;
  constructor(public url: string) {}
  send(d: unknown) {
    this.sent.push(d);
  }
  close() {
    this.closeCalls++;
    this.readyState = 3;
    this.onclose?.();
  }
  // helpers
  open() {
    this.readyState = FakeWs.OPEN;
    this.onopen?.();
  }
  recv(data: unknown) {
    this.onmessage?.({ data });
  }
}

const fakeTimers = () => {
  let now = 0;
  const intervals = new Map<number, { fn: () => void; ms: number }>();
  const timeouts = new Map<number, { fn: () => void; at: number }>();
  let id = 0;
  return {
    timers: {
      setInterval: ((fn: () => void, ms: number) => {
        const i = ++id;
        intervals.set(i, { fn, ms });
        return i as unknown as ReturnType<typeof setInterval>;
      }) as typeof setInterval,
      clearInterval: ((i: ReturnType<typeof setInterval>) => {
        intervals.delete(i as unknown as number);
      }) as typeof clearInterval,
      setTimeout: ((fn: () => void, ms: number) => {
        const i = ++id;
        timeouts.set(i, { fn, at: now + ms });
        return i as unknown as ReturnType<typeof setTimeout>;
      }) as typeof setTimeout,
      now: () => now,
    },
    advance(ms: number) {
      now += ms;
      for (const [i, t] of [...timeouts]) {
        if (t.at <= now) {
          timeouts.delete(i);
          t.fn();
        }
      }
    },
    tickInterval(i: number) {
      intervals.get(i)?.fn();
    },
    firstInterval() {
      return [...intervals.values()][0];
    },
  };
};

describe("createWsClient", () => {
  it("connects, fires status, and emits parsed JSON envelopes", () => {
    const messages: unknown[] = [];
    const statuses: string[] = [];
    let last: FakeWs | null = null;
    const client = createWsClient({
      url: "ws://x",
      onMessage: (m) => messages.push(m),
      onStatus: (s) => statuses.push(s),
      webSocketFactory: (u) => {
        last = new FakeWs(u) as unknown as WebSocket & FakeWs;
        return last as unknown as WebSocket;
      },
      autoReconnect: false,
    });
    expect(statuses).toEqual(["connecting"]);
    last!.open();
    expect(statuses).toContain("open");
    last!.recv(JSON.stringify({ type: "hello", payload: { a: 1 } }));
    expect(messages).toEqual([
      { type: "hello", payload: { a: 1 } },
    ]);
    expect(client.status).toBe("open");
  });

  it("passes ArrayBuffer through unchanged (audio binary frames)", () => {
    const messages: unknown[] = [];
    let last: FakeWs | null = null;
    createWsClient({
      url: "ws://x",
      onMessage: (m) => messages.push(m),
      webSocketFactory: (u) => {
        last = new FakeWs(u) as unknown as WebSocket & FakeWs;
        return last as unknown as WebSocket;
      },
      autoReconnect: false,
    });
    last!.open();
    const buf = new ArrayBuffer(8);
    last!.recv(buf);
    expect(messages[0]).toBe(buf);
  });

  it("filters out pong frames and refreshes deadline", () => {
    const messages: unknown[] = [];
    let last: FakeWs | null = null;
    createWsClient({
      url: "ws://x",
      onMessage: (m) => messages.push(m),
      webSocketFactory: (u) => {
        last = new FakeWs(u) as unknown as WebSocket & FakeWs;
        return last as unknown as WebSocket;
      },
      autoReconnect: false,
    });
    last!.open();
    last!.recv(JSON.stringify({ type: "pong", ts: 1 }));
    expect(messages).toEqual([]);
  });

  it("send() serializes envelopes and stamps seq + ts", () => {
    let last: FakeWs | null = null;
    const ctrl = fakeTimers();
    const client = createWsClient({
      url: "ws://x",
      onMessage: () => undefined,
      webSocketFactory: (u) => {
        last = new FakeWs(u) as unknown as WebSocket & FakeWs;
        return last as unknown as WebSocket;
      },
      timers: ctrl.timers,
      autoReconnect: false,
    });
    last!.open();
    client.send({ type: "audio.start" });
    const sent = JSON.parse(last!.sent.at(-1) as string);
    expect(sent.type).toBe("audio.start");
    expect(sent.seq).toBeGreaterThan(0);
    expect(typeof sent.ts).toBe("number");
  });

  it("send() forwards ArrayBuffer untouched", () => {
    let last: FakeWs | null = null;
    const client = createWsClient({
      url: "ws://x",
      onMessage: () => undefined,
      webSocketFactory: (u) => {
        last = new FakeWs(u) as unknown as WebSocket & FakeWs;
        return last as unknown as WebSocket;
      },
      autoReconnect: false,
    });
    last!.open();
    const buf = new ArrayBuffer(4);
    client.send(buf);
    expect(last!.sent.at(-1)).toBe(buf);
  });

  it("reports JSON parse errors via onError without crashing", () => {
    const onError = vi.fn();
    let last: FakeWs | null = null;
    createWsClient({
      url: "ws://x",
      onMessage: () => undefined,
      onError,
      webSocketFactory: (u) => {
        last = new FakeWs(u) as unknown as WebSocket & FakeWs;
        return last as unknown as WebSocket;
      },
      autoReconnect: false,
    });
    last!.open();
    last!.recv("{not-json");
    expect(onError).toHaveBeenCalledOnce();
  });

  it("auto-reconnects with backoff after onclose", () => {
    const ctrl = fakeTimers();
    const factories: FakeWs[] = [];
    createWsClient({
      url: "ws://x",
      onMessage: () => undefined,
      webSocketFactory: (u) => {
        const w = new FakeWs(u);
        factories.push(w);
        return w as unknown as WebSocket;
      },
      timers: ctrl.timers,
      backoff: [10, 20],
    });
    expect(factories).toHaveLength(1);
    factories[0].open();
    factories[0].onclose?.(); // simulate drop (not closeByUser)
    // first backoff = 10
    ctrl.advance(10);
    expect(factories).toHaveLength(2);
  });

  it("close() prevents reconnect", () => {
    const ctrl = fakeTimers();
    const factories: FakeWs[] = [];
    const client = createWsClient({
      url: "ws://x",
      onMessage: () => undefined,
      webSocketFactory: (u) => {
        const w = new FakeWs(u);
        factories.push(w);
        return w as unknown as WebSocket;
      },
      timers: ctrl.timers,
      backoff: [10],
    });
    factories[0].open();
    client.close();
    ctrl.advance(1000);
    expect(factories).toHaveLength(1);
  });
});
