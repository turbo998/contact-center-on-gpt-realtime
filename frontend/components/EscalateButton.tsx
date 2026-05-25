"use client";

import { useState } from "react";
import { useStore } from "@/lib/store";

interface Props {
  /** Called when user clicks; should send escalate.request envelope on Agent WS. */
  onEscalate?: (snapshot: {
    callId: string | null;
    reasoning: ReturnType<typeof useStore.getState>["reasoning"];
    toolCalls: ReturnType<typeof useStore.getState>["toolCalls"];
  }) => void;
}

/** Agent-only button: requests human escalation, passing a snapshot of AI assist state. */
export function EscalateButton({ onEscalate }: Props) {
  const [sent, setSent] = useState(false);
  const handle = () => {
    const s = useStore.getState();
    onEscalate?.({
      callId: s.callId,
      reasoning: s.reasoning,
      toolCalls: s.toolCalls,
    });
    setSent(true);
  };
  return (
    <button
      type="button"
      onClick={handle}
      disabled={sent}
      aria-label="升级人工"
      className="px-3 py-2 rounded-md text-sm font-medium bg-amber-100 text-amber-800 hover:bg-amber-200 disabled:opacity-60 disabled:cursor-not-allowed"
    >
      {sent ? "已升级人工" : "升级人工"}
    </button>
  );
}
