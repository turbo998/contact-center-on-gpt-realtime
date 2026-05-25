import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useStore } from "@/lib/store";
import { EscalateButton } from "./EscalateButton";

describe("EscalateButton", () => {
  it("renders default label", () => {
    render(<EscalateButton />);
    expect(screen.getByRole("button", { name: "升级人工" })).toBeTruthy();
  });

  it("on click invokes onEscalate with current store snapshot then disables", () => {
    useStore.setState({
      callId: "c-1",
      reasoning: [{ id: "r1", index: 0, summary: "s", startedAt: 0 }],
      toolCalls: [],
    });
    const onEscalate = vi.fn();
    render(<EscalateButton onEscalate={onEscalate} />);
    const btn = screen.getByRole("button", { name: "升级人工" });
    fireEvent.click(btn);
    expect(onEscalate).toHaveBeenCalledOnce();
    const arg = onEscalate.mock.calls[0][0];
    expect(arg.callId).toBe("c-1");
    expect(arg.reasoning).toHaveLength(1);
    // After click, button is in disabled "已升级人工" state
    const btn2 = screen.getByRole("button", { name: "升级人工" });
    expect(btn2.hasAttribute("disabled")).toBe(true);
    expect(btn2.textContent).toBe("已升级人工");
  });
});
