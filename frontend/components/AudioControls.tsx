"use client";
import { useCallback, useRef, useState } from "react";
import clsx from "clsx";
import { startRecorder, type RecorderHandle } from "@/lib/audio/recorder";

export interface AudioControlsProps {
  /** Visual accent — matches owning pane. */
  variant: "customer" | "agent";
  /** Called per 20ms PCM16 frame while recording. */
  onFrame?: (pcm16: ArrayBuffer) => void;
  /** Disable if WS not connected, etc. */
  disabled?: boolean;
}

const ACCENT: Record<AudioControlsProps["variant"], string> = {
  customer: "bg-customer-500 hover:bg-customer-700",
  agent: "bg-agent-500 hover:bg-agent-700",
};

export function AudioControls({ variant, onFrame, disabled }: AudioControlsProps) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handleRef = useRef<RecorderHandle | null>(null);

  const start = useCallback(async () => {
    setError(null);
    try {
      const h = await startRecorder({ onFrame: onFrame ?? (() => undefined) });
      handleRef.current = h;
      setRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [onFrame]);

  const stop = useCallback(async () => {
    const h = handleRef.current;
    handleRef.current = null;
    setRecording(false);
    if (h) await h.stop();
  }, []);

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        data-testid="mic-toggle"
        aria-pressed={recording}
        disabled={disabled}
        onClick={() => (recording ? void stop() : void start())}
        className={clsx(
          "rounded-md px-3 py-1.5 text-sm font-medium text-white transition-colors disabled:bg-slate-400",
          recording ? "bg-rose-600 hover:bg-rose-700" : ACCENT[variant],
        )}
      >
        {recording ? "■ Stop" : "● Record"}
      </button>
      {error && (
        <span role="alert" className="text-xs text-rose-600">
          {error}
        </span>
      )}
    </div>
  );
}
