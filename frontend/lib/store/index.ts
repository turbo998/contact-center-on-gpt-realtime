import { create } from "zustand";
import type { RootStore } from "./types";
import { createCallSlice } from "./callSlice";
import { createTranscriptSlice } from "./transcriptSlice";
import { createAssistSlice } from "./assistSlice";

export const useStore = create<RootStore>()((...a) => ({
  ...createCallSlice(...a),
  ...createTranscriptSlice(...a),
  ...createAssistSlice(...a),
}));

export type { RootStore } from "./types";
