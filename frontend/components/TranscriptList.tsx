"use client";
import { useStore } from "@/lib/store";
import type { Speaker } from "@/lib/store/types";

interface Props {
  /** Filter transcripts to one speaker. */
  speaker?: Speaker;
  emptyHint: string;
}

export function TranscriptList({ speaker, emptyHint }: Props) {
  const utts = useStore((s) =>
    speaker ? s.utterances.filter((u) => u.speaker === speaker) : s.utterances,
  );
  if (utts.length === 0) {
    return <div className="text-xs italic text-slate-400">{emptyHint}</div>;
  }
  return (
    <ul className="space-y-2" data-testid="transcript-list">
      {utts.map((u) => (
        <li
          key={u.id}
          className="rounded-md bg-white/70 px-2 py-1.5 shadow-sm"
          data-final={u.isFinal}
        >
          <div className="text-xs uppercase text-slate-400">
            {u.speaker} · {u.lang}
            {!u.isFinal && <span className="ml-1 text-amber-600">…</span>}
          </div>
          <div className="text-sm text-slate-900">{u.text}</div>
          {u.translation && (
            <div className="text-xs text-slate-500 italic">↳ {u.translation}</div>
          )}
        </li>
      ))}
    </ul>
  );
}
