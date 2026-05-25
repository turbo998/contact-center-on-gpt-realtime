import clsx from "clsx";

export type Status = "ok" | "idle" | "error" | "warn";

const COLORS: Record<Status, string> = {
  ok: "bg-emerald-500",
  idle: "bg-slate-400",
  warn: "bg-amber-500",
  error: "bg-red-500",
};

export function StatusBadge({ status, label }: { status: Status; label: string }) {
  return (
    <span
      data-testid={`status-${status}`}
      className="inline-flex items-center gap-1.5 rounded-full bg-slate-50 px-2 py-0.5 text-xs text-slate-700"
    >
      <span className={clsx("inline-block h-2 w-2 rounded-full", COLORS[status])} />
      {label}
    </span>
  );
}
