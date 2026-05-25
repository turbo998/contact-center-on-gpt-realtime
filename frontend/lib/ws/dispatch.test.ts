import { describe, it, expect, beforeEach, vi } from "vitest";
import { useStore } from "../store";
import type { Envelope } from "../types";
import { dispatch } from "./dispatch";

const store = {
  getState: useStore.getState,
  setState: useStore.setState,
};

const env = <T,>(type: string, payload: T, over: Partial<Envelope<T>> = {}): Envelope<T> => ({
  v: 1,
  type,
  ts: 1000,
  call_id: "c-1",
  seq: 1,
  payload,
  ...over,
});

beforeEach(() => {
  useStore.setState({
    callId: null,
    status: "idle",
    startedAt: null,
    endedAt: null,
    error: null,
    utterances: [],
    reasoning: [],
    toolCalls: [],
    finalText: "",
    audioPlaying: false,
  });
});

describe("dispatch — call lifecycle", () => {
  it("call.started → startCall", () => {
    dispatch(store, env("call.started", { call_id: "c-1", voice: "alloy", started_at: 0 }), { channel: "customer" });
    expect(useStore.getState().status).toBe("live");
    expect(useStore.getState().callId).toBe("c-1");
  });

  it("call.ended → endCall", () => {
    useStore.getState().startCall("c-1");
    dispatch(store, env("call.ended", { duration_ms: 1000, audit_url: "" }), { channel: "customer" });
    expect(useStore.getState().status).toBe("ended");
  });

  it("error → setError", () => {
    dispatch(store, env("error", { code: "E_AUTH_FAILED", message: "nope" }), { channel: "customer" });
    expect(useStore.getState().status).toBe("error");
    expect(useStore.getState().error).toContain("E_AUTH_FAILED");
  });
});

describe("dispatch — transcripts", () => {
  it("first whisper.transcript.delta inserts; second appends", () => {
    dispatch(store, env("whisper.transcript.delta", { text: "你", is_final: false }), { channel: "customer" });
    dispatch(store, env("whisper.transcript.delta", { text: "好", is_final: false }), { channel: "customer" });
    const u = useStore.getState().utterances;
    expect(u).toHaveLength(1);
    expect(u[0].text).toBe("你好");
    expect(u[0].speaker).toBe("customer");
  });

  it("is_final=true finalizes the current utterance", () => {
    dispatch(store, env("whisper.transcript.delta", { text: "hi", is_final: true }), { channel: "customer" });
    expect(useStore.getState().utterances[0].isFinal).toBe(true);
  });

  it("whisper.transcript.completed replaces rolling current with final utt_id", () => {
    dispatch(store, env("whisper.transcript.delta", { text: "你", is_final: false }), { channel: "customer" });
    dispatch(store, env("whisper.transcript.completed", { text: "你好", utt_id: "u-1" }), { channel: "customer" });
    const u = useStore.getState().utterances;
    expect(u).toHaveLength(1);
    expect(u[0].id).toBe("u-1");
    expect(u[0].text).toBe("你好");
    expect(u[0].isFinal).toBe(true);
  });

  it("channel=agent attributes transcript to agent speaker", () => {
    dispatch(store, env("whisper.transcript.delta", { text: "hello", is_final: true }), { channel: "agent" });
    expect(useStore.getState().utterances[0].speaker).toBe("agent");
  });

  it("translate.text.delta appends translation to last customer utterance", () => {
    useStore.getState().upsertUtterance({
      id: "u-1", speaker: "customer", lang: "zh", text: "你好", isFinal: true, startMs: 0,
    });
    dispatch(store, env("translate.text.delta", { text: "Hel", direction: "customer_to_agent", is_final: false }), { channel: "customer" });
    dispatch(store, env("translate.text.delta", { text: "lo", direction: "customer_to_agent", is_final: true }), { channel: "customer" });
    expect(useStore.getState().utterances[0].translation).toBe("Hello");
  });
});

describe("dispatch — audio sink", () => {
  it("translate.audio.delta routes to onAudio with source=translate", () => {
    const onAudio = vi.fn();
    dispatch(store, env("translate.audio.delta", { audio: "AAAA" }), { channel: "customer", onAudio });
    expect(onAudio).toHaveBeenCalledWith("AAAA", "translate");
  });

  it("audio.frame.out on assist channel routes with source=assist", () => {
    const onAudio = vi.fn();
    dispatch(store, env("audio.frame.out", { audio: "BBBB", duration_ms: 20 }), { channel: "assist", onAudio });
    expect(onAudio).toHaveBeenCalledWith("BBBB", "assist");
  });
});

describe("dispatch — rt2 assist stream", () => {
  it("rt2.reasoning.delta appends per step id", () => {
    dispatch(store, env("rt2.reasoning.delta", { text: "Look", step: 0 }), { channel: "assist" });
    dispatch(store, env("rt2.reasoning.delta", { text: "ing up order...", step: 0 }), { channel: "assist" });
    dispatch(store, env("rt2.reasoning.delta", { text: "Found it", step: 1 }), { channel: "assist" });
    const r = useStore.getState().reasoning;
    expect(r).toHaveLength(2);
    expect(r[0].summary).toBe("Looking up order...");
    expect(r[1].summary).toBe("Found it");
  });

  it("rt2.tool.call → addToolCall, rt2.tool.result → success", () => {
    dispatch(store, env("rt2.tool.call", { call_id: "t-1", name: "lookup_order", arguments: { id: "X" } }), { channel: "assist" });
    dispatch(store, env("rt2.tool.result", { call_id: "t-1", name: "lookup_order", result: { ok: true }, duration_ms: 50, ok: true }), { channel: "assist" });
    const t = useStore.getState().toolCalls[0];
    expect(t.status).toBe("success");
    expect(t.result).toEqual({ ok: true });
  });

  it("rt2.tool.result ok=false marks status=error", () => {
    dispatch(store, env("rt2.tool.call", { call_id: "t-2", name: "x", arguments: {} }), { channel: "assist" });
    dispatch(store, env("rt2.tool.result", { call_id: "t-2", name: "x", result: {}, duration_ms: 1, ok: false }), { channel: "assist" });
    expect(useStore.getState().toolCalls[0].status).toBe("error");
  });

  it("rt2.text.delta accumulates finalText", () => {
    dispatch(store, env("rt2.text.delta", { text: "Hello " }), { channel: "assist" });
    dispatch(store, env("rt2.text.delta", { text: "world" }), { channel: "assist" });
    expect(useStore.getState().finalText).toBe("Hello world");
  });

  it("rt2.done sets audioPlaying=false", () => {
    useStore.getState().setAudioPlaying(true);
    dispatch(store, env("rt2.done", { total_tokens: 100, reasoning_tokens: 10, tool_calls_count: 1 }), { channel: "assist" });
    expect(useStore.getState().audioPlaying).toBe(false);
  });

  it("unknown type is silently ignored", () => {
    expect(() =>
      dispatch(store, env("future.feature.x", {}), { channel: "assist" }),
    ).not.toThrow();
  });
});
