import { describe, it, expect } from "vitest";
import { startRecorder } from "./recorder";

describe("recorder", () => {
  it("exports startRecorder as a function", () => {
    expect(typeof startRecorder).toBe("function");
  });

  it("rejects when called without browser mediaDevices", async () => {
    // jsdom has no mediaDevices by default — verifies the guard.
    await expect(
      startRecorder({ onFrame: () => undefined }),
    ).rejects.toThrow(/mediaDevices/);
  });
});
