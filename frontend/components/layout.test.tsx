/**
 * TDD red-first tests for #14 frontend-layout.
 * Spec: docs/14-frontend-design.md §14.1 / §14.2 / §14.8.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThreePane } from "./ThreePane";
import { CustomerPane } from "./CustomerPane";
import { AgentPane } from "./AgentPane";
import { AssistPane } from "./AssistPane";
import { Header } from "./Header";
import { StatusBadge } from "./StatusBadge";

describe("ThreePane", () => {
  it("renders all three panes when role=both", () => {
    render(<ThreePane role="both" />);
    expect(screen.getByTestId("customer-pane")).toBeTruthy();
    expect(screen.getByTestId("agent-pane")).toBeTruthy();
    expect(screen.getByTestId("assist-pane")).toBeTruthy();
  });

  it("renders only customer pane when role=customer", () => {
    render(<ThreePane role="customer" />);
    expect(screen.getByTestId("customer-pane")).toBeTruthy();
    expect(screen.queryByTestId("agent-pane")).toBeNull();
    expect(screen.queryByTestId("assist-pane")).toBeNull();
  });

  it("renders agent + assist when role=agent", () => {
    render(<ThreePane role="agent" />);
    expect(screen.queryByTestId("customer-pane")).toBeNull();
    expect(screen.getByTestId("agent-pane")).toBeTruthy();
    expect(screen.getByTestId("assist-pane")).toBeTruthy();
  });

  it("uses grid layout classes for responsive 3-col", () => {
    const { container } = render(<ThreePane role="both" />);
    const main = container.querySelector("main");
    expect(main?.className).toMatch(/grid/);
    expect(main?.className).toMatch(/xl:grid-cols-3/);
  });
});

describe("Pane components", () => {
  it("CustomerPane uses customer color token", () => {
    const { container } = render(<CustomerPane />);
    expect(container.innerHTML).toMatch(/customer-/);
    expect(screen.getByText(/客户|Customer/i)).toBeTruthy();
  });

  it("AgentPane uses agent color token", () => {
    const { container } = render(<AgentPane />);
    expect(container.innerHTML).toMatch(/agent-/);
    expect(screen.getByRole("heading", { name: /Agent|坐席/i })).toBeTruthy();
  });

  it("AssistPane uses assist color token", () => {
    const { container } = render(<AssistPane />);
    expect(container.innerHTML).toMatch(/assist-/);
    expect(screen.getByText(/Assist|AI/i)).toBeTruthy();
  });
});

describe("Header", () => {
  it("renders branding text", () => {
    render(<Header />);
    expect(screen.getByText(/Contact Center/i)).toBeTruthy();
  });
});

describe("StatusBadge", () => {
  it("renders ok variant with emerald color", () => {
    const { container } = render(<StatusBadge status="ok" label="Live" />);
    expect(container.innerHTML).toMatch(/emerald/);
    expect(screen.getByText("Live")).toBeTruthy();
  });
  it("renders idle variant with slate color", () => {
    const { container } = render(<StatusBadge status="idle" label="Idle" />);
    expect(container.innerHTML).toMatch(/slate/);
  });
  it("renders error variant with red color", () => {
    const { container } = render(<StatusBadge status="error" label="Err" />);
    expect(container.innerHTML).toMatch(/red/);
  });
});
