"use client";

import { useState } from "react";
import type { ReasoningStep } from "@/lib/store/types";

interface Props {
  step: ReasoningStep;
}

function formatDuration(step: ReasoningStep): string {
  if (!step.endedAt) return "...";
  const ms = step.endedAt - step.startedAt;
  return `${ms}ms`;
}

export function ReasoningCard({ step }: Props) {
  const [open, setOpen] = useState(false);
  const hasDetail = Boolean(step.detail);
  return (
    <div
      data-testid={`reasoning-${step.id}`}
      className="border border-assist-200 bg-assist-50 rounded-md p-2 text-sm"
    >
      <button
        type="button"
        onClick={() => hasDetail && setOpen((v) => !v)}
        className="w-full flex justify-between items-start text-left"
        aria-expanded={open}
        aria-label={`reasoning step ${step.index + 1}`}
      >
        <span className="flex-1 text-assist-900 whitespace-pre-wrap">
          <span className="font-medium mr-2">#{step.index + 1}</span>
          {step.summary}
        </span>
        <span className="ml-2 text-xs text-assist-700 shrink-0">
          {formatDuration(step)}
        </span>
      </button>
      {open && hasDetail && (
        <pre className="mt-2 text-xs bg-white p-2 rounded border border-assist-200 overflow-x-auto whitespace-pre-wrap">
          {step.detail}
        </pre>
      )}
    </div>
  );
}
