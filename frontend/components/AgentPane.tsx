import { StatusBadge } from "./StatusBadge";
import { AudioControls } from "./AudioControls";

export function AgentPane() {
  return (
    <section data-testid="agent-pane" className="flex h-full min-h-[40vh] flex-col bg-agent-50">
      <div className="flex items-center justify-between border-b border-agent-500/20 px-4 py-2">
        <div>
          <h2 className="text-sm font-semibold text-agent-700">坐席端 · Agent (EN)</h2>
          <p className="text-xs text-slate-500">whisper STT · 单向英文转写</p>
        </div>
        <StatusBadge status="idle" label="Idle" />
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <div className="text-xs italic text-slate-400">
          Transcript stream binds to <code>/ws/agent</code> in issue #16.
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-agent-500/20 bg-white/60 p-3">
        <AudioControls variant="agent" />
        <button
          type="button"
          className="rounded-xl bg-assist-500 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-assist-700 disabled:opacity-40"
          disabled
        >
          🆘 Escalate to GPT-Realtime-2
        </button>
      </div>
    </section>
  );
}
