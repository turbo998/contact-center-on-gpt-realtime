import type { StateCreator } from "zustand";
import type {
  AssistActions,
  AssistState,
  ReasoningStep,
  RootStore,
  ToolCall,
} from "./types";

export const createAssistSlice: StateCreator<
  RootStore,
  [],
  [],
  AssistState & AssistActions
> = (set) => ({
  reasoning: [],
  toolCalls: [],
  finalText: "",
  audioPlaying: false,

  addReasoning: (step: ReasoningStep) =>
    set((state) => ({ reasoning: [...state.reasoning, step] })),

  updateReasoning: (id, patch) =>
    set((state) => {
      const idx = state.reasoning.findIndex((r) => r.id === id);
      if (idx === -1) return state;
      const next = state.reasoning.slice();
      next[idx] = { ...next[idx], ...patch };
      return { reasoning: next };
    }),

  addToolCall: (tc: ToolCall) =>
    set((state) => ({ toolCalls: [...state.toolCalls, tc] })),

  updateToolCall: (id, patch) =>
    set((state) => {
      const idx = state.toolCalls.findIndex((t) => t.id === id);
      if (idx === -1) return state;
      const next = state.toolCalls.slice();
      next[idx] = { ...next[idx], ...patch };
      return { toolCalls: next };
    }),

  appendFinalText: (delta) =>
    set((state) => ({ finalText: state.finalText + delta })),

  setAudioPlaying: (b) => set({ audioPlaying: b }),

  resetAssist: () =>
    set({ reasoning: [], toolCalls: [], finalText: "", audioPlaying: false }),
});
