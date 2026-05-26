import { describe, it, expect } from "vitest";
import { createCallSession } from "./session";
import { createStore } from "zustand/vanilla";
import type { RootStore } from "../store/types";
import { createCallSlice } from "../store/callSlice";
import { createTranscriptSlice } from "../store/transcriptSlice";
import { createAssistSlice } from "../store/assistSlice";

/** Vanilla store mirror for tests (UI uses zustand/react). */
function makeStore() {
  return createStore<RootStore>()((...a) => ({
    ...createCallSlice(...a),
    ...createTranscriptSlice(...a),
    ...createAssistSlice(...a),
  }));
}

class FakeWs {
  static OPEN = 1;
  binaryType = "";
  readyState = 0;
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;
  sent: string[] = [];
  closeCalls = 0;
  constructor(public url: string) {}
  send(d: unknown) {
    this.sent.push(String(d));
  }
  close() {
    this.closeCalls++;
    this.readyState = 3;
    this.onclose?.();
  }
  open() {
    this.readyState = FakeWs.OPEN;
    this.onopen?.();
  }
  recv(data: unknown) {
    this.onmessage?.({ data });
  }
}

describe("createCallSession", () => {
  it("sends call.start envelope on open with channel-appropriate role/lang", () => {
    let ws: FakeWs | null = null;
    const session = createCallSession({
      url: "ws://x/ws/customer",
      callId: "c-1",
      channel: "customer",
      store: makeStore(),
      webSocketFactory: (u) => {
        ws = new FakeWs(u) as unknown as WebSocket;
        return ws as unknown as WebSocket;
      },
    });
    ws!.open();
    const env = JSON.parse(ws!.sent[0]);
    expect(env.type).toBe("call.start");
    expect(env.call_id).toBe("c-1");
    expect(env.payload).toMatchObject({ role: "customer", lang: "zh-CN", target_lang: "en-US" });
    session.close();
  });

  it("wraps PCM16 ArrayBuffer into audio.frame envelope with base64 audio", () => {
    let ws: FakeWs | null = null;
    const session = createCallSession({
      url: "ws://x/ws/customer",
      callId: "c-2",
      channel: "customer",
      store: makeStore(),
      webSocketFactory: (u) => {
        ws = new FakeWs(u) as unknown as WebSocket;
        return ws as unknown as WebSocket;
      },
    });
    ws!.open();
    ws!.sent.length = 0; // discard call.start
    const buf = new Uint8Array([0x01, 0x02, 0x03, 0x04]).buffer;
    session.sendAudioFrame(buf);
    const env = JSON.parse(ws!.sent[0]);
    expect(env.type).toBe("audio.frame");
    expect(env.payload.audio).toBe("AQIDBA==");
    expect(env.payload.duration_ms).toBe(20);
    session.close();
  });

  it("dispatches incoming envelopes into the store", () => {
    let ws: FakeWs | null = null;
    const store = makeStore();
    createCallSession({
      url: "ws://x/ws/customer",
      callId: "c-3",
      channel: "customer",
      store,
      webSocketFactory: (u) => {
        ws = new FakeWs(u) as unknown as WebSocket;
        return ws as unknown as WebSocket;
      },
    });
    ws!.open();
    ws!.recv(
      JSON.stringify({
        v: 1,
        type: "call.started",
        call_id: "c-3",
        seq: 1,
        ts: 0,
        payload: { call_id: "c-3", voice: "alloy", started_at: 0 },
      }),
    );
    expect(store.getState().callId).toBe("c-3");
    expect(store.getState().status).toBe("live");

    ws!.recv(
      JSON.stringify({
        v: 1,
        type: "whisper.transcript.delta",
        call_id: "c-3",
        seq: 2,
        ts: 1,
        payload: { text: "你好", is_final: false },
      }),
    );
    expect(store.getState().utterances).toHaveLength(1);
    expect(store.getState().utterances[0].text).toBe("你好");
    expect(store.getState().utterances[0].speaker).toBe("customer");
  });

  it("forwards translate.audio.delta to onAudio sink", () => {
    let ws: FakeWs | null = null;
    const got: Array<{ b64: string; src: string }> = [];
    createCallSession({
      url: "ws://x/ws/customer",
      callId: "c-4",
      channel: "customer",
      store: makeStore(),
      onAudio: (b64, src) => got.push({ b64, src }),
      webSocketFactory: (u) => {
        ws = new FakeWs(u) as unknown as WebSocket;
        return ws as unknown as WebSocket;
      },
    });
    ws!.open();
    ws!.recv(
      JSON.stringify({
        v: 1,
        type: "translate.audio.delta",
        call_id: "c-4",
        seq: 1,
        ts: 0,
        payload: { audio: "AAAA", direction: "customer_to_agent" },
      }),
    );
    expect(got).toEqual([{ b64: "AAAA", src: "translate" }]);
  });

  it("end() sends call.end and close() closes the socket", () => {
    let ws: FakeWs | null = null;
    const session = createCallSession({
      url: "ws://x/ws/customer",
      callId: "c-5",
      channel: "customer",
      store: makeStore(),
      webSocketFactory: (u) => {
        ws = new FakeWs(u) as unknown as WebSocket;
        return ws as unknown as WebSocket;
      },
    });
    ws!.open();
    ws!.sent.length = 0;
    session.end();
    const env = JSON.parse(ws!.sent[0]);
    expect(env.type).toBe("call.end");
    expect(env.payload.reason).toBe("user_hangup");
    session.close();
    expect(ws!.closeCalls).toBe(1);
  });

  it("agent channel sends role=agent with English lang", () => {
    let ws: FakeWs | null = null;
    createCallSession({
      url: "ws://x/ws/agent",
      callId: "c-6",
      channel: "agent",
      store: makeStore(),
      webSocketFactory: (u) => {
        ws = new FakeWs(u) as unknown as WebSocket;
        return ws as unknown as WebSocket;
      },
    });
    ws!.open();
    const env = JSON.parse(ws!.sent[0]);
    expect(env.payload).toMatchObject({ role: "agent", lang: "en-US", target_lang: "zh-CN" });
  });
});
