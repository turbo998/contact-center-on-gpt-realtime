import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./index";

const reset = () =>
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

beforeEach(reset);

describe("callSlice", () => {
  it("startCall sets status=live and timestamps", () => {
    useStore.getState().startCall("c-1");
    const s = useStore.getState();
    expect(s.callId).toBe("c-1");
    expect(s.status).toBe("live");
    expect(s.startedAt).toBeGreaterThan(0);
    expect(s.endedAt).toBeNull();
  });

  it("endCall transitions to ended", () => {
    useStore.getState().startCall("c-1");
    useStore.getState().endCall();
    expect(useStore.getState().status).toBe("ended");
    expect(useStore.getState().endedAt).toBeGreaterThan(0);
  });

  it("setError flips status to error and stores message", () => {
    useStore.getState().setError("boom");
    expect(useStore.getState().status).toBe("error");
    expect(useStore.getState().error).toBe("boom");
  });
});

describe("transcriptSlice", () => {
  const u = (id: string, over: Partial<Parameters<typeof useStore.getState>[0] extends never ? never : never> = {}) => ({
    id,
    speaker: "customer" as const,
    lang: "zh" as const,
    text: "",
    isFinal: false,
    startMs: 0,
    ...over,
  });

  it("upsertUtterance inserts then patches by id", () => {
    useStore.getState().upsertUtterance(u("u1"));
    useStore.getState().upsertUtterance({ ...u("u1"), text: "你好" });
    const ut = useStore.getState().utterances;
    expect(ut).toHaveLength(1);
    expect(ut[0].text).toBe("你好");
  });

  it("appendDelta accumulates text and translation independently", () => {
    useStore.getState().upsertUtterance(u("u1"));
    useStore.getState().appendDelta("u1", "Hel", "text");
    useStore.getState().appendDelta("u1", "lo", "text");
    useStore.getState().appendDelta("u1", "你", "translation");
    useStore.getState().appendDelta("u1", "好", "translation");
    const ut = useStore.getState().utterances[0];
    expect(ut.text).toBe("Hello");
    expect(ut.translation).toBe("你好");
  });

  it("appendDelta no-ops when id unknown", () => {
    useStore.getState().appendDelta("missing", "x", "text");
    expect(useStore.getState().utterances).toHaveLength(0);
  });

  it("finalize marks isFinal=true and sets endMs", () => {
    useStore.getState().upsertUtterance(u("u1"));
    useStore.getState().finalize("u1");
    const ut = useStore.getState().utterances[0];
    expect(ut.isFinal).toBe(true);
    expect(ut.endMs).toBeGreaterThan(0);
  });

  it("clear removes all utterances", () => {
    useStore.getState().upsertUtterance(u("u1"));
    useStore.getState().clear();
    expect(useStore.getState().utterances).toEqual([]);
  });
});

describe("assistSlice", () => {
  it("addReasoning + updateReasoning patches by id", () => {
    useStore.getState().addReasoning({
      id: "r1",
      index: 0,
      summary: "thinking",
      startedAt: 1,
    });
    useStore.getState().updateReasoning("r1", { endedAt: 2, detail: "done" });
    const r = useStore.getState().reasoning[0];
    expect(r.endedAt).toBe(2);
    expect(r.detail).toBe("done");
  });

  it("addToolCall + updateToolCall patches by id", () => {
    useStore.getState().addToolCall({
      id: "t1",
      name: "lookup_order",
      args: { id: "X" },
      status: "pending",
      startedAt: 1,
    });
    useStore.getState().updateToolCall("t1", {
      status: "success",
      result: { ok: true },
      endedAt: 2,
    });
    const t = useStore.getState().toolCalls[0];
    expect(t.status).toBe("success");
    expect(t.result).toEqual({ ok: true });
  });

  it("appendFinalText accumulates", () => {
    useStore.getState().appendFinalText("Hello ");
    useStore.getState().appendFinalText("world");
    expect(useStore.getState().finalText).toBe("Hello world");
  });

  it("resetAssist clears all assist state", () => {
    useStore.getState().appendFinalText("x");
    useStore.getState().setAudioPlaying(true);
    useStore.getState().resetAssist();
    const s = useStore.getState();
    expect(s.finalText).toBe("");
    expect(s.audioPlaying).toBe(false);
    expect(s.reasoning).toEqual([]);
    expect(s.toolCalls).toEqual([]);
  });
});
