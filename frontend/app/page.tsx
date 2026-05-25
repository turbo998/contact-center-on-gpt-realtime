"use client";
/**
 * Single-page three-pane workspace.
 * See docs/14-frontend-design.md §14.1.
 */
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Header } from "@/components/Header";
import { ThreePane, type Role } from "@/components/ThreePane";

function PageInner() {
  const param = useSearchParams().get("role");
  const role: Role = param === "customer" || param === "agent" ? param : "both";
  return (
    <div className="flex min-h-screen flex-col bg-slate-100 text-slate-900">
      <Header />
      <ThreePane role={role} />
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<div className="p-4 text-sm text-slate-500">Loading…</div>}>
      <PageInner />
    </Suspense>
  );
}
