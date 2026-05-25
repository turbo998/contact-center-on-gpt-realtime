import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AudioControls } from "./AudioControls";

describe("AudioControls", () => {
  it("renders idle Record button with customer accent", () => {
    const { container } = render(<AudioControls variant="customer" />);
    const btn = screen.getByTestId("mic-toggle");
    expect(btn.textContent).toMatch(/Record/);
    expect(btn.getAttribute("aria-pressed")).toBe("false");
    expect(container.innerHTML).toMatch(/customer-500/);
  });

  it("shows error toast when start() fails (no mediaDevices in jsdom)", async () => {
    render(<AudioControls variant="agent" />);
    fireEvent.click(screen.getByTestId("mic-toggle"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/mediaDevices/);
    });
  });

  it("respects disabled prop", () => {
    render(<AudioControls variant="agent" disabled />);
    expect((screen.getByTestId("mic-toggle") as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not call onFrame when not recording", () => {
    const onFrame = vi.fn();
    render(<AudioControls variant="customer" onFrame={onFrame} />);
    expect(onFrame).not.toHaveBeenCalled();
  });
});
