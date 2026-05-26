/**
 * High-level call session — owns one WsClient + a PCMPlayer.
 *
 * Responsibilities:
 *  - Send the spec-required `call.start` envelope on socket open.
 *  - Wrap PCM16 ArrayBuffer mic frames as base64 `audio.frame` envelopes.
 *  - Route incoming envelopes through the WS `dispatch` into the zustand store.
 *  - Forward outbound translate/assist audio payloads to an injected PCMPlayer sink.
 *
 * `webSocketFactory` is an injection seam — production uses the global
 * WebSocket constructor; tests inject a FakeWs.
 *
 * Spec: docs/11-api-contract.md §11.2 / §11.3, docs/14-frontend-design.md §14.7.
 */

import { createWsClient, type WsClient, type WsEnvelope } from "../ws/client";
import { dispatch } from "../ws/dispatch";
import type { RootStore } from "../store/types";

export type Channel = "customer" | "agent" | "assist";

export interface CallSessionOpts {
  url: string;
  callId: string;
  channel: Channel;
  store: {
    getState: () => RootStore;
    setState: (partial: Partial<RootStore>) => void;
  };
  /** Sink for inbound base64 PCM16 audio (translate or assist). */
  onAudio?: (b64: string, source: "translate" | "assist") => void;
  /** Error hook (mirrors WsClient onError). */
  onError?: (err: Event | Error) => void;
  /** Status hook (mirrors WsClient onStatus). */
  onStatus?: (s: "connecting" | "open" | "closed") => void;
  /** Test seam — defaults to global WebSocket. */
  webSocketFactory?: (url: string) => WebSocket;
}

export interface CallSession {
  /** Send one 20ms PCM16 frame (ArrayBuffer, 960 bytes @ 24kHz mono). */
  sendAudioFrame: (pcm16: ArrayBuffer) => void;
  /** Send `call.end` envelope (graceful hangup). */
  end: () => void;
  /** Close the underlying WebSocket. */
  close: () => void;
}

const LANG_BY_CHANNEL: Record<Channel, { lang: string; target: string }> = {
  customer: { lang: "zh-CN", target: "en-US" },
  agent: { lang: "en-US", target: "zh-CN" },
  assist: { lang: "en-US", target: "en-US" },
};

function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  if (typeof btoa === "function") return btoa(bin);
  // Node fallback (tests)
  return Buffer.from(bytes).toString("base64");
}

export function createCallSession(opts: CallSessionOpts): CallSession {
  const { callId, channel, store, onAudio } = opts;
  const langCfg = LANG_BY_CHANNEL[channel];

  let client: WsClient | null = null;
  let opened = false;

  client = createWsClient({
    url: opts.url,
    webSocketFactory: opts.webSocketFactory,
    onError: opts.onError,
    onStatus: (s) => {
      opts.onStatus?.(s);
      if (s === "open" && !opened) {
        opened = true;
        // Spec §11.2.3: first frame must be call.start.
        client?.send({
          v: 1,
          type: "call.start",
          call_id: callId,
          payload: {
            role: channel === "agent" ? "agent" : "customer",
            lang: langCfg.lang,
            target_lang: langCfg.target,
          },
        });
      }
    },
    onMessage: (msg) => {
      if (msg instanceof ArrayBuffer) return; // not used today
      const env = msg as WsEnvelope;
      // Cast: dispatch expects its own Envelope shape — they're structurally
      // identical at runtime (type+payload+call_id+seq+ts).
      dispatch(
        store as Parameters<typeof dispatch>[0],
        env as unknown as Parameters<typeof dispatch>[1],
        { channel, onAudio },
      );
    },
  });

  return {
    sendAudioFrame(pcm16) {
      if (!client) return;
      client.send({
        v: 1,
        type: "audio.frame",
        call_id: callId,
        payload: {
          audio: arrayBufferToBase64(pcm16),
          duration_ms: 20,
        },
      });
    },
    end() {
      client?.send({
        v: 1,
        type: "call.end",
        call_id: callId,
        payload: { reason: "user_hangup" },
      });
    },
    close() {
      client?.close();
      client = null;
    },
  };
}
