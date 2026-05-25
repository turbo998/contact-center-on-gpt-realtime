"use client";

import { useStore } from "@/lib/store";
import { StatusBadge } from "./StatusBadge";
import { ReasoningCard } from "./ReasoningCard";
import { ToolCallTable } from "./ToolCallTable";

export function AssistPane() {
  const reasoning = useStore((s) => s.reasoning);
  const toolCalls = useStore((s) => s.toolCalls);
  const finalText = useStore((s) => s.finalText);
  const audioPlaying = useStore((s) => s.audioPlaying);

  const isLive = reasoning.length > 0 || toolCalls.length > 0 || finalText.length > 0;

  return (
    <section
      data-testid="assist-pane"
      className="flex h-full min-h-[40vh] flex-col bg-assist-50"
    >
      <div className="flex items-center justify-between border-b border-assist-500/20 px-4 py-2">
        <div>
          <h2 className="text-sm font-semibold text-assist-700">
            AI Assist · GPT-Realtime-2
          </h2>
          <p className="text-xs text-slate-500">
            reasoning trace · tool calls · final answer
          </p>
        </div>
        <StatusBadge
          status={isLive ? "ok" : "idle"}
          label={isLive ? "Escalated" : "Not escalated"}
        />
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Reasoning */}
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm">
          <div className="text-xs font-medium uppercase text-assist-700 mb-2">
            Reasoning
          </div>
          {reasoning.length === 0 ? (
            <div className="text-xs italic text-slate-400">
              Pending escalation…
            </div>
          ) : (
            <div data-testid="reasoning-list" className="space-y-2">
              {reasoning.map((step) => (
                <ReasoningCard key={step.id} step={step} />
              ))}
            </div>
          )}
        </div>

        {/* Tool calls */}
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm">
          <div className="text-xs font-medium uppercase text-assist-700 mb-2">
            Tool calls
          </div>
          <ToolCallTable toolCalls={toolCalls} />
        </div>

        {/* Final answer */}
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-medium uppercase text-assist-700">
              Final answer
            </div>
            {audioPlaying && (
              <span
                role="status"
                aria-label="audio playing"
                className="text-xs text-assist-600 animate-pulse"
              >
                ▶ 播放中
              </span>
            )}
          </div>
          {finalText ? (
            <p
              data-testid="final-text"
              className="text-sm text-slate-800 whitespace-pre-wrap"
            >
              {finalText}
            </p>
          ) : (
            <div className="text-xs italic text-slate-400">—</div>
          )}
        </div>
      </div>
    </section>
  );
}
