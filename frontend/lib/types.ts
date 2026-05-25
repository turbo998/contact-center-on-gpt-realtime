// WebSocket protocol types — see ../../docs/11-api-contract.md §11.6
// Single source of truth for all message shapes across /ws/customer, /ws/agent, /ws/assist.

export const PROTOCOL_VERSION = 1 as const;
export type ProtocolVersion = typeof PROTOCOL_VERSION;

export interface Envelope<T = unknown> {
  v: ProtocolVersion;
  type: string;
  ts: number;
  call_id: string;
  seq: number;
  payload: T;
}

export type Role = "customer" | "agent";
export type TranslateDirection = "customer_to_agent" | "agent_to_customer";
export type ReasoningEffort = "minimal" | "low" | "medium" | "high";

// --- Customer / Agent shared ---
export interface CallStartPayload {
  role: Role;
  lang: string;
  target_lang: string;
}
export interface AudioFramePayload {
  audio: string; // base64 PCM16 LE, 24kHz mono, 20ms
  duration_ms: number;
}
export interface CallEndPayload {
  reason: "user_hangup" | "timeout" | "error";
}
export interface CallStartedPayload {
  call_id: string;
  voice: string;
  started_at: number;
}
export interface WhisperTranscriptDeltaPayload {
  text: string;
  is_final: boolean;
}
export interface WhisperTranscriptCompletedPayload {
  text: string;
  utt_id: string;
}
export interface TranslateTextDeltaPayload {
  text: string;
  direction: TranslateDirection;
  is_final: boolean;
}
export interface TranslateAudioDeltaPayload {
  audio: string;
  direction: TranslateDirection;
}
export interface TranslateAudioDonePayload {
  direction: TranslateDirection;
}
export interface CallEndedPayload {
  duration_ms: number;
  audit_url: string;
}

// --- /ws/agent only ---
export interface EscalateRequestPayload {
  order_id?: string;
  note?: string;
}
export interface EscalateAckedPayload {
  assist_ws_url: string;
  context_summary: string;
}

// --- /ws/assist ---
export interface AssistStartPayload {
  call_id: string;
  context_summary: string;
  order_id?: string;
  reasoning_effort?: ReasoningEffort;
}
export interface AssistStartedPayload {
  session_id: string;
  model: string;
  reasoning_effort: ReasoningEffort;
}
export interface Rt2ReasoningDeltaPayload {
  text: string;
  step: number;
}
export interface Rt2ToolCallPayload {
  call_id: string;
  name: string;
  arguments: Record<string, unknown>;
}
export interface Rt2ToolResultPayload {
  call_id: string;
  name: string;
  result: Record<string, unknown>;
  duration_ms: number;
  ok: boolean;
}
export interface Rt2DonePayload {
  total_tokens: number;
  reasoning_tokens: number;
  tool_calls_count: number;
}

// --- Error ---
export type ErrorCode =
  | "E_AUTH_FAILED"
  | "E_FOUNDRY_DISCONNECT"
  | "E_AUDIO_FORMAT"
  | "E_AUDIO_TOO_LARGE"
  | "E_ESCALATE_NO_CONTEXT"
  | "E_TOOL_TIMEOUT"
  | "E_TOOL_UNKNOWN"
  | "E_RATE_LIMIT"
  | "E_SESSION_EXPIRED"
  | "E_INTERNAL";

export interface ErrorPayload {
  code: ErrorCode | string;
  message: string;
  retriable: boolean;
  details?: Record<string, unknown>;
}

// ============================================================================
// Helpers
// ============================================================================

export class ProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProtocolError";
  }
}

/** Build a v1 envelope. ``ts`` defaults to ``Date.now()``. */
export function makeEnvelope<T>(args: {
  type: string;
  call_id: string;
  seq: number;
  payload: T;
  ts?: number;
}): Envelope<T> {
  return {
    v: PROTOCOL_VERSION,
    type: args.type,
    ts: args.ts ?? Date.now(),
    call_id: args.call_id,
    seq: args.seq,
    payload: args.payload,
  };
}

const REQUIRED_FIELDS = ["v", "type", "ts", "call_id", "seq", "payload"] as const;

/** Parse a wire frame, validating envelope shape and protocol version. */
export function parseEnvelope<T = unknown>(raw: string): Envelope<T> {
  let obj: unknown;
  try {
    obj = JSON.parse(raw);
  } catch (e) {
    throw new ProtocolError(`invalid JSON: ${(e as Error).message}`);
  }
  if (typeof obj !== "object" || obj === null || Array.isArray(obj)) {
    throw new ProtocolError("envelope must be a JSON object");
  }
  const rec = obj as Record<string, unknown>;
  for (const f of REQUIRED_FIELDS) {
    if (!(f in rec)) throw new ProtocolError(`envelope missing required field: ${f}`);
  }
  if (rec.v !== PROTOCOL_VERSION) {
    throw new ProtocolError(`unsupported protocol version: ${String(rec.v)}`);
  }
  return rec as unknown as Envelope<T>;
}
