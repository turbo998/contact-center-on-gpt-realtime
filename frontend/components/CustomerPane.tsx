import { StatusBadge } from "./StatusBadge";

export function CustomerPane() {
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
        <StatusBadge status="idle" label="未连接" />
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <div className="text-xs italic text-slate-400">
          字幕将在 WebSocket 连接后实时显示（issue #16）。
        </div>
      </div>
      <div className="border-t border-customer-500/20 bg-white/60 p-3">
        <div className="text-xs text-slate-500">麦克风控制 — 待 issue #15 接入</div>
      </div>
    </section>
  );
}
