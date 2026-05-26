"use client";
import { StatusBadge, type Status } from "./StatusBadge";
import { AudioControls } from "./AudioControls";
import { EscalateButton } from "./EscalateButton";
import { TranscriptList } from "./TranscriptList";
import { useCallSession } from "@/lib/session/useCallSession";

interface Props {
  onEscalate?: Parameters<typeof EscalateButton>[0]["onEscalate"];
}

const STATUS_MAP: Record<"connecting" | "open" | "closed", { s: Status; label: string }> = {
  connecting: { s: "warn", label: "Connecting…" },
  open: { s: "ok", label: "Live" },
  closed: { s: "idle", label: "Idle" },
};

export function AgentPane({ onEscalate }: Props = {}) {
  const { status, sendFrame, error } = useCallSession("agent");
  const badge = STATUS_MAP[status];
  return (
    <section data-testid="agent-pane" className="flex h-full min-h-[40vh] flex-col bg-agent-50">
      <div className="flex items-center justify-between border-b border-agent-500/20 px-4 py-2">
        <div>
          <h2 className="text-sm font-semibold text-agent-700">坐席端 · Agent (EN)</h2>
          <p className="text-xs text-slate-500">whisper STT · 单向英文转写</p>
        </div>
        <StatusBadge status={error ? "error" : badge.s} label={error ?? badge.label} />
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <TranscriptList speaker="agent" emptyHint="Press Record to stream mic to /ws/agent." />
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-agent-500/20 bg-white/60 p-3">
        <AudioControls variant="agent" onFrame={sendFrame} disabled={status !== "open"} />
        <EscalateButton onEscalate={onEscalate} />
      </div>
    </section>
  );
}
