/**
 * Reconnecting WebSocket client.
 * Spec: docs/14-frontend-design.md §14.6.
 *
 * - Exponential backoff reconnect: 1s/2s/4s/8s (capped)
 * - 15s ping / 20s pong deadline heartbeat
 * - Binary frames pass through unchanged (audio); JSON envelopes are parsed
 *
 * `webSocketFactory` is injected for testability (defaults to global `WebSocket`).
 */

export interface WsEnvelope<T = unknown> {
  v?: number;
  type: string;
  call_id?: string;
  seq?: number;
  ts?: number;
  payload?: T;
}

export type WsStatus = "connecting" | "open" | "closed";

export interface WsClientOpts {
  url: string;
  onMessage: (msg: WsEnvelope | ArrayBuffer) => void;
  onError?: (err: Event | Error) => void;
  onStatus?: (s: WsStatus) => void;
  /** Test seam — defaults to global WebSocket. */
  webSocketFactory?: (url: string) => WebSocket;
  /** Test seam — defaults to setInterval/setTimeout/Date.now. */
  timers?: {
    setInterval: typeof setInterval;
    clearInterval: typeof clearInterval;
    setTimeout: typeof setTimeout;
    now: () => number;
  };
  /** Disable automatic reconnect (tests). */
  autoReconnect?: boolean;
  /** Backoff schedule (ms). */
  backoff?: readonly number[];
  /** Ping interval ms (default 15000). */
  pingMs?: number;
  /** Pong deadline ms (default 20000). */
  pongDeadlineMs?: number;
}

export interface WsClient {
  send: (msg: WsEnvelope | ArrayBuffer) => void;
  close: () => void;
  readonly status: WsStatus;
}

const DEFAULT_BACKOFF = [1000, 2000, 4000, 8000] as const;

export function createWsClient(opts: WsClientOpts): WsClient {
  const factory = opts.webSocketFactory ?? ((u: string) => new WebSocket(u));
  const T = opts.timers ?? {
    setInterval,
    clearInterval,
    setTimeout,
    now: () => Date.now(),
  };
  const backoff = opts.backoff ?? DEFAULT_BACKOFF;
  const pingMs = opts.pingMs ?? 15000;
  const pongDeadlineMs = opts.pongDeadlineMs ?? 20000;
  const autoReconnect = opts.autoReconnect ?? true;

  let ws: WebSocket | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let pongDeadline = 0;
  let attempt = 0;
  let closedByUser = false;
  let seq = 0;
  let status: WsStatus = "connecting";

  const setStatus = (s: WsStatus) => {
    status = s;
    opts.onStatus?.(s);
  };

  const stopHeartbeat = () => {
    if (pingTimer) {
      T.clearInterval(pingTimer);
      pingTimer = null;
    }
  };

  const connect = () => {
    setStatus("connecting");
    ws = factory(opts.url);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      attempt = 0;
      setStatus("open");
      pongDeadline = T.now() + pongDeadlineMs;
      pingTimer = T.setInterval(() => {
        if (T.now() > pongDeadline) {
          ws?.close();
          return;
        }
        ws?.send(JSON.stringify({ type: "ping", ts: T.now(), seq: ++seq }));
      }, pingMs);
    };

    ws.onmessage = (ev: MessageEvent) => {
      if (ev.data instanceof ArrayBuffer) {
        opts.onMessage(ev.data);
        return;
      }
      try {
        const msg = JSON.parse(String(ev.data)) as WsEnvelope;
        if (msg.type === "pong") {
          pongDeadline = T.now() + pongDeadlineMs;
          return;
        }
        opts.onMessage(msg);
      } catch (e) {
        opts.onError?.(e as Error);
      }
    };

    ws.onerror = (e: Event) => opts.onError?.(e);

    ws.onclose = () => {
      stopHeartbeat();
      setStatus("closed");
      if (closedByUser || !autoReconnect) return;
      const delay = backoff[Math.min(attempt, backoff.length - 1)];
      attempt++;
      T.setTimeout(connect, delay);
    };
  };

  connect();

  return {
    get status() {
      return status;
    },
    send: (msg) => {
      if (!ws || ws.readyState !== 1 /* OPEN */) return;
      if (msg instanceof ArrayBuffer) {
        ws.send(msg);
      } else {
        ws.send(
          JSON.stringify({ ...msg, seq: ++seq, ts: msg.ts ?? T.now() }),
        );
      }
    },
    close: () => {
      closedByUser = true;
      stopHeartbeat();
      ws?.close();
    },
  };
}
