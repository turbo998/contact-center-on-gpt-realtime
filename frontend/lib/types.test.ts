import { describe, expect, it } from "vitest";
import {
  PROTOCOL_VERSION,
  ProtocolError,
  makeEnvelope,
  parseEnvelope,
  type AudioFramePayload,
  type CallStartPayload,
  type Envelope,
  type ErrorPayload,
} from "./types";

describe("makeEnvelope", () => {
  it("defaults v=1 and current ts", () => {
    const env = makeEnvelope<CallStartPayload>({
      type: "call.start",
      call_id: "C-1",
      seq: 0,
      payload: { role: "customer", lang: "zh-CN", target_lang: "en-US" },
    });
    expect(env.v).toBe(PROTOCOL_VERSION);
    expect(env.type).toBe("call.start");
    expect(env.call_id).toBe("C-1");
    expect(env.seq).toBe(0);
    expect(env.payload.role).toBe("customer");
    expect(Math.abs(env.ts - Date.now())).toBeLessThan(5000);
  });

  it("accepts explicit ts", () => {
    const env = makeEnvelope({ type: "x", call_id: "C", seq: 1, payload: {}, ts: 999 });
    expect(env.ts).toBe(999);
  });
});

describe("parseEnvelope", () => {
  it("roundtrips JSON.stringify -> parseEnvelope", () => {
    const env = makeEnvelope<AudioFramePayload>({
      type: "audio.frame",
      call_id: "C-7",
      seq: 42,
      payload: { audio: "AAA=", duration_ms: 20 },
    });
    const parsed = parseEnvelope<AudioFramePayload>(JSON.stringify(env));
    expect(parsed).toEqual(env);
  });

  it("rejects invalid JSON", () => {
    expect(() => parseEnvelope("not json {")).toThrow(ProtocolError);
  });

  it("rejects non-object root", () => {
    expect(() => parseEnvelope("[]")).toThrow(ProtocolError);
    expect(() => parseEnvelope("42")).toThrow(ProtocolError);
    expect(() => parseEnvelope("null")).toThrow(ProtocolError);
  });

  it("rejects missing fields", () => {
    expect(() => parseEnvelope('{"v":1,"type":"x"}')).toThrow(/missing required field/);
  });

  it("rejects unsupported version", () => {
    const bad = '{"v":2,"type":"x","ts":1,"call_id":"C","seq":0,"payload":{}}';
    expect(() => parseEnvelope(bad)).toThrow(/unsupported protocol version/);
  });
});

describe("ErrorPayload typing", () => {
  it("constructs a valid error envelope", () => {
    const env = makeEnvelope<ErrorPayload>({
      type: "error.raised",
      call_id: "C-1",
      seq: 99,
      payload: { code: "E_TOOL_TIMEOUT", message: "took too long", retriable: true },
    });
    expect(env.payload.code).toBe("E_TOOL_TIMEOUT");
    expect(env.payload.retriable).toBe(true);
  });
});

describe("Envelope generic", () => {
  it("preserves payload type", () => {
    const env: Envelope<{ x: number }> = {
      v: 1,
      type: "t",
      ts: 1,
      call_id: "C",
      seq: 0,
      payload: { x: 5 },
    };
    expect(env.payload.x).toBe(5);
  });
});
