import { StatusBadge } from "./StatusBadge";

export function AssistPane() {
  return (
    <section data-testid="assist-pane" className="flex h-full min-h-[40vh] flex-col bg-assist-50">
      <div className="flex items-center justify-between border-b border-assist-500/20 px-4 py-2">
        <div>
          <h2 className="text-sm font-semibold text-assist-700">AI Assist · GPT-Realtime-2</h2>
          <p className="text-xs text-slate-500">reasoning trace · tool calls · final answer</p>
        </div>
        <StatusBadge status="idle" label="Not escalated" />
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm">
          <div className="text-xs font-medium uppercase text-assist-700">Reasoning</div>
          <div className="mt-1 text-xs italic text-slate-400">Pending escalation…</div>
        </div>
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm">
          <div className="text-xs font-medium uppercase text-assist-700">Tool calls</div>
          <div className="mt-1 text-xs italic text-slate-400">—</div>
        </div>
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm">
          <div className="text-xs font-medium uppercase text-assist-700">Final answer</div>
          <div className="mt-1 text-xs italic text-slate-400">—</div>
        </div>
      </div>
    </section>
  );
}
