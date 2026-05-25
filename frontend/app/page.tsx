/**
 * Single-page three-pane workspace.
 * See docs/14-frontend-design.md §14.1.
 * TODO (issue #12 frontend-layout): implement ThreePane + role param.
 */
export default function HomePage() {
  return (
    <main className="grid min-h-screen grid-cols-1 lg:grid-cols-3 gap-2 p-4">
      <section className="rounded-2xl bg-blue-50 p-4">Customer Pane (ZH) — TODO</section>
      <section className="rounded-2xl bg-emerald-50 p-4">Agent Pane (EN) — TODO</section>
      <section className="rounded-2xl bg-violet-50 p-4">AI Assist Pane — TODO</section>
    </main>
  );
}
