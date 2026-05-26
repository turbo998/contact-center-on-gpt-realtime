"use client";
/**
 * React hook wrapping createCallSession.
 *
 * One session per channel per mount. Inbound audio is streamed into a
 * lazily-constructed PCMPlayer (created only when the first audio arrives,
 * so SSR / unit tests without AudioContext don't blow up).
 *
 * Returns:
 *   status     — WS lifecycle: "connecting" | "open" | "closed"
 *   sendFrame  — pass to <AudioControls onFrame> to push mic PCM16
 *   end        — graceful hangup
 */
import { useEffect, useRef, useState } from "react";
import { createCallSession, type Channel } from "./session";
import { wsUrl } from "../config";
import { useStore } from "../store";
import { PCMPlayer } from "../audio/player";
function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
}

const PATHS: Record<Channel, string> = {
  customer: "/ws/customer",
  agent: "/ws/agent",
  assist: "/ws/assist",
};

/** Stable, per-tab call id shared across panes (so customer + agent + assist join the same call). */
function tabCallId(): string {
  if (typeof window === "undefined") return "ssr";
  const KEY = "ccgpt.callId";
  let id = window.sessionStorage.getItem(KEY);
  if (!id) {
    id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `c-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    window.sessionStorage.setItem(KEY, id);
  }
  return id;
}

export interface UseCallSessionResult {
  status: "connecting" | "open" | "closed";
  sendFrame: (pcm16: ArrayBuffer) => void;
  end: () => void;
  error: string | null;
}

export function useCallSession(channel: Channel): UseCallSessionResult {
  const [status, setStatus] = useState<UseCallSessionResult["status"]>("connecting");
  const [error, setError] = useState<string | null>(null);
  const sessionRef = useRef<ReturnType<typeof createCallSession> | null>(null);
  const playerRef = useRef<PCMPlayer | null>(null);

  useEffect(() => {
    const callId = tabCallId();
    const url = wsUrl(PATHS[channel], { call_id: callId });

    const session = createCallSession({
      url,
      callId,
      channel,
      store: {
        getState: useStore.getState,
        setState: (p) => useStore.setState(p as Parameters<typeof useStore.setState>[0]),
      },
      onStatus: setStatus,
      onError: (e) => setError(e instanceof Error ? e.message : "ws error"),
      onAudio: (b64) => {
        try {
          if (!playerRef.current) playerRef.current = new PCMPlayer({});
          playerRef.current.enqueue(base64ToArrayBuffer(b64));
        } catch {
          // No AudioContext (SSR/test) — silently drop.
        }
      },
    });
    sessionRef.current = session;

    return () => {
      session.close();
      sessionRef.current = null;
    };
  }, [channel]);

  return {
    status,
    error,
    sendFrame: (buf) => sessionRef.current?.sendAudioFrame(buf),
    end: () => sessionRef.current?.end(),
  };
}
