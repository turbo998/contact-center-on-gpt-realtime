/**
 * Maps WebSocket envelope `type` → store actions.
 * See docs/11-api-contract.md §11.6 + docs/14-frontend-design.md §14.3.
 *
 * Designed pure: takes a store API + envelope, returns void.
 * Easy to test by stubbing the store object.
 */

import type {
  AudioFramePayload,
  CallEndedPayload,
  CallStartedPayload,
  Envelope,
  Rt2DonePayload,
  Rt2ReasoningDeltaPayload,
  Rt2ToolCallPayload,
  Rt2ToolResultPayload,
  TranslateTextDeltaPayload,
  WhisperTranscriptCompletedPayload,
  WhisperTranscriptDeltaPayload,
} from "../types";
import type { RootStore, Speaker } from "../store/types";

export interface StoreApi {
  getState: () => RootStore;
  setState: (partial: Partial<RootStore>) => void;
}

export interface DispatchOpts {
  /** Which channel this envelope arrived on — used to attribute Whisper transcripts to a speaker. */
  channel: "customer" | "agent" | "assist";
  /** Sink for raw audio payloads (player) — base64 PCM16. */
  onAudio?: (b64: string, source: "translate" | "assist") => void;
}

export function dispatch(
  store: StoreApi,
  env: Envelope,
  opts: DispatchOpts,
): void {
  const s = store.getState();
  switch (env.type) {
    case "call.started": {
      const p = env.payload as CallStartedPayload;
      s.startCall(p.call_id);
      return;
    }

    case "call.ended": {
      const _p = env.payload as CallEndedPayload;
      s.endCall();
      return;
    }

    case "whisper.transcript.delta": {
      const p = env.payload as WhisperTranscriptDeltaPayload;
      const speaker: Speaker = opts.channel === "agent" ? "agent" : "customer";
      const id = `${env.call_id}:${speaker}:current`;
      const existing = s.utterances.find((u) => u.id === id);
      if (!existing) {
        s.upsertUtterance({
          id,
          speaker,
          lang: speaker === "customer" ? "zh" : "en",
          text: p.text,
          isFinal: false,
          startMs: env.ts,
        });
      } else {
        s.appendDelta(id, p.text, "text");
      }
      if (p.is_final) s.finalize(id);
      return;
    }

    case "whisper.transcript.completed": {
      const p = env.payload as WhisperTranscriptCompletedPayload;
      const speaker: Speaker = opts.channel === "agent" ? "agent" : "customer";
      s.upsertUtterance({
        id: p.utt_id,
        speaker,
        lang: speaker === "customer" ? "zh" : "en",
        text: p.text,
        isFinal: true,
        startMs: env.ts,
        endMs: env.ts,
      });
      // Drop the rolling "current" placeholder if present
      const currentId = `${env.call_id}:${speaker}:current`;
      if (s.utterances.some((u) => u.id === currentId)) {
        store.setState({
          utterances: store
            .getState()
            .utterances.filter((u) => u.id !== currentId),
        });
      }
      return;
    }

    case "translate.text.delta": {
      const p = env.payload as TranslateTextDeltaPayload;
      // Attach translation to the most recent utterance of the source speaker.
      const sourceSpeaker: Speaker =
        p.direction === "customer_to_agent" ? "customer" : "agent";
      const list = s.utterances.filter((u) => u.speaker === sourceSpeaker);
      const target = list.at(-1);
      if (!target) return;
      s.appendDelta(target.id, p.text, "translation");
      return;
    }

    case "translate.audio.delta": {
      const p = env.payload as { audio: string };
      opts.onAudio?.(p.audio, "translate");
      return;
    }

    case "translate.audio.done":
      // No-op for store; player handles flush via its own jitter buffer.
      return;

    case "audio.frame.out": {
      // Generic outbound audio frame (assist TTS or similar)
      const p = env.payload as AudioFramePayload;
      opts.onAudio?.(p.audio, opts.channel === "assist" ? "assist" : "translate");
      return;
    }

    case "rt2.reasoning.delta": {
      const p = env.payload as Rt2ReasoningDeltaPayload;
      const id = `r:${env.call_id}:${p.step}`;
      const existing = s.reasoning.find((r) => r.id === id);
      if (!existing) {
        s.addReasoning({
          id,
          index: p.step,
          summary: p.text,
          startedAt: env.ts,
        });
      } else {
        s.updateReasoning(id, { summary: existing.summary + p.text });
      }
      return;
    }

    case "rt2.tool.call": {
      const p = env.payload as Rt2ToolCallPayload;
      s.addToolCall({
        id: p.call_id,
        name: p.name,
        args: p.arguments,
        status: "pending",
        startedAt: env.ts,
      });
      return;
    }

    case "rt2.tool.result": {
      const p = env.payload as Rt2ToolResultPayload;
      s.updateToolCall(p.call_id, {
        result: p.result,
        status: p.ok ? "success" : "error",
        endedAt: env.ts,
      });
      return;
    }

    case "rt2.text.delta": {
      const p = env.payload as { text: string };
      s.appendFinalText(p.text);
      return;
    }

    case "rt2.done": {
      const _p = env.payload as Rt2DonePayload;
      // Mark assist as no longer streaming audio
      s.setAudioPlaying(false);
      return;
    }

    case "error": {
      const p = env.payload as { code: string; message: string };
      s.setError(`${p.code}: ${p.message}`);
      return;
    }

    default:
      // Unknown type — drop silently (forward-compat)
      return;
  }
}
