/**
 * #19 E2E (jsdom) — escalate flow:
 *   1. Agent clicks EscalateButton → onEscalate callback fires with snapshot.
 *   2. Backend (simulated) replies with assist channel events:
 *      rt2.reasoning.delta → rt2.tool_call → rt2.tool_result → rt2.text.delta → rt2.done.
 *   3. AssistPane re-renders reasoning cards, tool call rows, final answer.
 *
 * Wires through the REAL `dispatch()` to catch envelope-type contract drift
 * (spec uses underscore — see docs/11-api-contract.md §11.6).
 */
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { useStore } from "@/lib/store";
import { dispatch } from "@/lib/ws/dispatch";
import { AssistPane } from "@/components/AssistPane";
import { EscalateButton } from "@/components/EscalateButton";
import type { Envelope } from "@/lib/types";

const CALL_ID = "call-e2e-1";

const reset = () =>
  useStore.setState({
    callId: CALL_ID,
    reasoning: [],
    toolCalls: [],
    finalText: "",
    audioPlaying: false,
    utterances: [],
  });

const env = (type: string, payload: unknown, ts = 1_700_000_000): Envelope =>
  ({ v: 1, seq: 0, ts, channel: "assist", type, call_id: CALL_ID, payload }) as unknown as Envelope;

beforeEach(reset);

describe("escalate flow e2e (vitest+jsdom)", () => {
  it("clicking Escalate then streaming assist events updates AssistPane end-to-end", () => {
    // Render Agent-side widgets.
    const escalated: Array<{ callId: string | null }> = [];
    render(
      <div>
        <EscalateButton onEscalate={(snap) => escalated.push(snap)} />
        <AssistPane />
      </div>,
    );

    // 0) initial state: pending
    expect(screen.getByText("Pending escalation…")).toBeTruthy();
    expect(screen.getByText("Not escalated")).toBeTruthy();

    // 1) agent click
    fireEvent.click(screen.getByRole("button", { name: "升级人工" }));
    expect(escalated).toHaveLength(1);
    expect(escalated[0].callId).toBe(CALL_ID);

    // 2) simulate assist WS stream via real dispatch()
    const store = { getState: useStore.getState, setState: useStore.setState };
    const opts = { channel: "assist" as const };

    act(() => {
      dispatch(store, env("rt2.reasoning.delta", { step: 0, text: "Looking up order " }), opts);
      dispatch(store, env("rt2.reasoning.delta", { step: 0, text: "A12345" }), opts);
      dispatch(
        store,
        env("rt2.tool_call", { call_id: "tc-1", name: "get_order", arguments: { order_id: "A12345" } }),
        opts,
      );
      dispatch(
        store,
        env("rt2.tool_result", { call_id: "tc-1", name: "get_order", result: { total: 99 }, ok: true, duration_ms: 30 }),
        opts,
      );
      dispatch(store, env("rt2.text.delta", { text: "Your refund of $99 " }), opts);
      dispatch(store, env("rt2.text.delta", { text: "has been processed." }), opts);
      dispatch(store, env("rt2.done", { reason: "stop" }), opts);
    });

    // 3) assertions on rendered UI
    expect(screen.getByText("Escalated")).toBeTruthy();
    expect(screen.getByText(/Looking up order A12345/)).toBeTruthy();
    expect(screen.getByText("get_order")).toBeTruthy();
    expect(screen.getByTestId("final-text").textContent).toBe(
      "Your refund of $99 has been processed.",
    );

    // Audio playing turns off on rt2.done
    expect(screen.queryByRole("status", { name: "audio playing" })).toBeNull();
  });

  it("error envelope surfaces via store.setError", () => {
    render(<AssistPane />);
    const store = { getState: useStore.getState, setState: useStore.setState };
    act(() => {
      dispatch(
        store,
        env("error", { code: "tool_timeout", message: "get_order exceeded 5s" }),
        { channel: "assist" },
      );
    });
    expect(useStore.getState().error).toMatch(/tool_timeout/);
  });
});
