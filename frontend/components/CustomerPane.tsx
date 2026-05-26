"use client";
import { StatusBadge, type Status } from "./StatusBadge";
import { AudioControls } from "./AudioControls";
import { TranscriptList } from "./TranscriptList";
import { useCallSession } from "@/lib/session/useCallSession";

const STATUS_MAP: Record<"connecting" | "open" | "closed", { s: Status; label: string }> = {
  connecting: { s: "warn", label: "连接中…" },
  open: { s: "ok", label: "已连接" },
  closed: { s: "idle", label: "未连接" },
};

export function CustomerPane() {
  const { status, sendFrame, error } = useCallSession("customer");
  const badge = STATUS_MAP[status];
  return (
    <section
      data-testid="customer-pane"
      className="flex h-full min-h-[40vh] flex-col bg-customer-50"
    >
      <div className="flex items-center justify-between border-b border-customer-500/20 px-4 py-2">
        <div>
          <h2 className="text-sm font-semibold text-customer-700">客户端 · Customer (ZH)</h2>
          <p className="text-xs text-slate-500">gpt-realtime-translate · 中文 ↔ 英文</p>
        </div>
        <StatusBadge status={error ? "error" : badge.s} label={error ?? badge.label} />
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <TranscriptList speaker="customer" emptyHint="开始录音后字幕将实时显示。" />
      </div>
      <div className="border-t border-customer-500/20 bg-white/60 p-3">
        <AudioControls variant="customer" onFrame={sendFrame} disabled={status !== "open"} />
      </div>
    </section>
  );
}
