import type { StateCreator } from "zustand";
import type {
  RootStore,
  TranscriptActions,
  TranscriptState,
  Utterance,
} from "./types";

export const createTranscriptSlice: StateCreator<
  RootStore,
  [],
  [],
  TranscriptState & TranscriptActions
> = (set) => ({
  utterances: [],

  upsertUtterance: (u: Utterance) =>
    set((state) => {
      const idx = state.utterances.findIndex((x) => x.id === u.id);
      if (idx === -1) return { utterances: [...state.utterances, u] };
      const next = state.utterances.slice();
      next[idx] = { ...next[idx], ...u };
      return { utterances: next };
    }),

  appendDelta: (id, deltaText, kind) =>
    set((state) => {
      const idx = state.utterances.findIndex((x) => x.id === id);
      if (idx === -1) return state;
      const u = state.utterances[idx];
      const patched: Utterance =
        kind === "text"
          ? { ...u, text: u.text + deltaText }
          : { ...u, translation: (u.translation ?? "") + deltaText };
      const next = state.utterances.slice();
      next[idx] = patched;
      return { utterances: next };
    }),

  finalize: (id) =>
    set((state) => {
      const idx = state.utterances.findIndex((x) => x.id === id);
      if (idx === -1) return state;
      const next = state.utterances.slice();
      next[idx] = { ...next[idx], isFinal: true, endMs: Date.now() };
      return { utterances: next };
    }),

  clear: () => set({ utterances: [] }),
});
