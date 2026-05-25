import type { StateCreator } from "zustand";
import type { CallActions, CallState, RootStore } from "./types";

export const createCallSlice: StateCreator<
  RootStore,
  [],
  [],
  CallState & CallActions
> = (set) => ({
  callId: null,
  status: "idle",
  startedAt: null,
  endedAt: null,
  error: null,

  startCall: (callId) =>
    set({
      callId,
      status: "live",
      startedAt: Date.now(),
      endedAt: null,
      error: null,
    }),
  setStatus: (status) => set({ status }),
  endCall: () => set({ status: "ended", endedAt: Date.now() }),
  setError: (msg) => set({ status: "error", error: msg }),
});
