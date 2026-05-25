import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useStore } from "@/lib/store";
import { AssistPane } from "./AssistPane";

const reset = () =>
  useStore.setState({
    reasoning: [],
    toolCalls: [],
    finalText: "",
    audioPlaying: false,
  });

beforeEach(reset);

describe("AssistPane", () => {
  it("shows 'Pending escalation' when no reasoning", () => {
    render(<AssistPane />);
    expect(screen.getByText("Pending escalation…")).toBeTruthy();
    expect(screen.getByText("Not escalated")).toBeTruthy();
  });

  it("renders reasoning cards from store, expands on click", () => {
    useStore.setState({
      reasoning: [
        { id: "r1", index: 0, summary: "Looking up order", detail: "DB query", startedAt: 0, endedAt: 50 },
      ],
    });
    render(<AssistPane />);
    expect(screen.getByText("Looking up order")).toBeTruthy();
    expect(screen.getByText("50ms")).toBeTruthy();
    // Detail hidden by default
    expect(screen.queryByText("DB query")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /reasoning step 1/i }));
    expect(screen.getByText("DB query")).toBeTruthy();
  });

  it("renders tool call rows with status dot and toggles args/result on click", () => {
    useStore.setState({
      toolCalls: [
        {
          id: "t1",
          name: "lookup_order",
          args: { id: "X-42" },
          result: { ok: true, total: 99 },
          status: "success",
          startedAt: 0,
          endedAt: 30,
        },
      ],
    });
    render(<AssistPane />);
    expect(screen.getByText("lookup_order")).toBeTruthy();
    expect(screen.getByText("30ms")).toBeTruthy();
    expect(screen.queryByText(/X-42/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /tool call lookup_order/i }));
    expect(screen.getByText(/X-42/)).toBeTruthy();
    expect(screen.getByText(/total/)).toBeTruthy();
  });

  it("renders final text and audio playing indicator", () => {
    useStore.setState({
      finalText: "Refund processed.",
      audioPlaying: true,
    });
    render(<AssistPane />);
    expect(screen.getByTestId("final-text").textContent).toBe(
      "Refund processed.",
    );
    expect(screen.getByRole("status", { name: "audio playing" })).toBeTruthy();
  });

  it("status badge flips to live when reasoning has entries", () => {
    useStore.setState({
      reasoning: [{ id: "r1", index: 0, summary: "x", startedAt: 0 }],
    });
    render(<AssistPane />);
    expect(screen.getByText("Escalated")).toBeTruthy();
  });
});
