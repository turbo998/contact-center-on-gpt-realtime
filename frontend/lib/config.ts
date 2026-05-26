/**
 * Resolve backend WebSocket URL.
 *
 * Priority:
 * 1. NEXT_PUBLIC_BACKEND_URL env (set at build/runtime, e.g. "https://ca-backend-xxx.azurecontainerapps.io")
 * 2. window.location.origin (same-origin deployment)
 *
 * Always returns the ws://|wss:// origin (no path).
 */
export function backendWsOrigin(): string {
  const raw =
    (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_BACKEND_URL) ||
    (typeof window !== "undefined" ? window.location.origin : "");
  if (!raw) return "";
  return raw.replace(/^http/, "ws").replace(/\/+$/, "");
}

export function wsUrl(path: string, params?: Record<string, string>): string {
  const origin = backendWsOrigin();
  const qs = params
    ? "?" +
      Object.entries(params)
        .filter(([, v]) => v != null && v !== "")
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join("&")
    : "";
  return `${origin}${path}${qs}`;
}
