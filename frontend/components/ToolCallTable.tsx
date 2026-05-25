"use client";

import { useState } from "react";
import type { ToolCall } from "@/lib/store/types";

interface RowProps {
  tc: ToolCall;
}

const STATUS_STYLE: Record<ToolCall["status"], string> = {
  pending: "bg-amber-400",
  success: "bg-emerald-500",
  error: "bg-rose-500",
};

function Row({ tc }: RowProps) {
  const [open, setOpen] = useState(false);
  const duration = tc.endedAt ? `${tc.endedAt - tc.startedAt}ms` : "...";
  return (
    <li
      data-testid={`tool-${tc.id}`}
      className="border-b border-slate-200 last:border-0 py-2"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`tool call ${tc.name}`}
        className="w-full flex items-center gap-2 text-sm text-left"
      >
        <span
          className={`inline-block w-2 h-2 rounded-full ${STATUS_STYLE[tc.status]}`}
          aria-label={`status ${tc.status}`}
        />
        <span className="font-mono text-slate-800">{tc.name}</span>
        <span className="ml-auto text-xs text-slate-500">{duration}</span>
      </button>
      {open && (
        <div className="mt-2 grid gap-2 text-xs">
          <div>
            <div className="text-slate-500 mb-1">args</div>
            <pre className="bg-slate-50 p-2 rounded border border-slate-200 overflow-x-auto">
              {JSON.stringify(tc.args, null, 2)}
            </pre>
          </div>
          {tc.result !== undefined && (
            <div>
              <div className="text-slate-500 mb-1">result</div>
              <pre className="bg-slate-50 p-2 rounded border border-slate-200 overflow-x-auto">
                {JSON.stringify(tc.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function ToolCallTable({ toolCalls }: { toolCalls: ToolCall[] }) {
  if (toolCalls.length === 0) {
    return (
      <p className="text-xs text-slate-400 italic">暂无工具调用</p>
    );
  }
  return (
    <ul className="divide-y divide-slate-200" data-testid="tool-call-table">
      {toolCalls.map((tc) => (
        <Row key={tc.id} tc={tc} />
      ))}
    </ul>
  );
}
