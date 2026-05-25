import { StatusBadge } from "./StatusBadge";

const BUILD = process.env.NEXT_PUBLIC_BUILD_ID ?? "dev";

export function Header() {
  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
      <div className="flex items-baseline gap-3">
        <h1 className="text-sm font-semibold text-slate-900">Contact Center on GPT-Realtime</h1>
        <span className="text-xs text-slate-400">build {BUILD}</span>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status="idle" label="rt-translate" />
        <StatusBadge status="idle" label="whisper" />
        <StatusBadge status="idle" label="rt-2" />
      </div>
    </header>
  );
}
