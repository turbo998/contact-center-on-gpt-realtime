/**
 * Zustand store slices — see docs/14-frontend-design.md §14.3.
 *
 * Types are kept here (single file) for cohesion; UI components import
 * the assembled `useStore` from './index'.
 */

// ---------- callSlice ----------
export type CallStatus = "idle" | "connecting" | "live" | "ended" | "error";

export interface CallState {
  callId: string | null;
  status: CallStatus;
  startedAt: number | null;
  endedAt: number | null;
  error: string | null;
}

export interface CallActions {
  startCall: (callId: string) => void;
  setStatus: (s: CallStatus) => void;
  endCall: () => void;
  setError: (msg: string) => void;
}

// ---------- transcriptSlice ----------
export type Speaker = "customer" | "agent";
export type Lang = "zh" | "en";

export interface Utterance {
  id: string;
  speaker: Speaker;
  lang: Lang;
  text: string;
  isFinal: boolean;
  translation?: string;
  startMs: number;
  endMs?: number;
}

export interface TranscriptState {
  utterances: Utterance[];
}

export interface TranscriptActions {
  upsertUtterance: (u: Utterance) => void;
  appendDelta: (
    id: string,
    deltaText: string,
    kind: "text" | "translation",
  ) => void;
  finalize: (id: string) => void;
  clear: () => void;
}

// ---------- assistSlice ----------
export interface ReasoningStep {
  id: string;
  index: number;
  summary: string;
  detail?: string;
  startedAt: number;
  endedAt?: number;
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
  status: "pending" | "success" | "error";
  startedAt: number;
  endedAt?: number;
}

export interface AssistState {
  reasoning: ReasoningStep[];
  toolCalls: ToolCall[];
  finalText: string;
  audioPlaying: boolean;
}

export interface AssistActions {
  addReasoning: (step: ReasoningStep) => void;
  updateReasoning: (id: string, patch: Partial<ReasoningStep>) => void;
  addToolCall: (tc: ToolCall) => void;
  updateToolCall: (id: string, patch: Partial<ToolCall>) => void;
  appendFinalText: (delta: string) => void;
  setAudioPlaying: (b: boolean) => void;
  resetAssist: () => void;
}

export type RootStore = CallState &
  CallActions &
  TranscriptState &
  TranscriptActions &
  AssistState &
  AssistActions;
