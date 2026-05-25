import clsx from "clsx";
import { CustomerPane } from "./CustomerPane";
import { AgentPane } from "./AgentPane";
import { AssistPane } from "./AssistPane";

export type Role = "both" | "customer" | "agent";

interface ThreePaneProps {
  role: Role;
  onEscalate?: Parameters<typeof AgentPane>[0] extends infer P
    ? P extends { onEscalate?: infer F }
      ? F
      : never
    : never;
}

export function ThreePane({ role, onEscalate }: ThreePaneProps) {
  const showCustomer = role === "both" || role === "customer";
  const showAgent = role === "both" || role === "agent";
  const showAssist = role === "both" || role === "agent";

  const cols = role === "both" ? "xl:grid-cols-3" : role === "agent" ? "xl:grid-cols-2" : "xl:grid-cols-1";

  return (
    <main
      className={clsx(
        "grid grid-cols-1 gap-px bg-slate-200 xl:h-[calc(100vh-3rem)]",
        cols,
      )}
    >
      {showCustomer && <CustomerPane />}
      {showAgent && <AgentPane onEscalate={onEscalate} />}
      {showAssist && <AssistPane />}
    </main>
  );
}
