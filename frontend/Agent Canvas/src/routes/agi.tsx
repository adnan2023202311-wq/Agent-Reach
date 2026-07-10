import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";

export const Route = createFileRoute("/agi")({
  component: AGIPage,
  head: () => ({ meta: [{ title: "AGI Readiness · Agent Reach Studio" }, { name: "description", content: "AGI readiness layer." }] }),
});

function AGIPage() {
  const onNavigate = useAppNavigation("agi");
  const topbar = useTopbar();

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="agi" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.20" title="AGI Readiness Layer" description="Long-horizon planning, recursive reasoning, autonomous objective management, and self-modeling." />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Long-Horizon Objectives</h3>
          <p className="text-sm text-muted-foreground">Create multi-step objectives with hierarchical decomposition. Track progress across sessions.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Recursive Reasoning</h3>
          <p className="text-sm text-muted-foreground">Self-reflective reasoning chains with configurable recursion depth. The system reasons about its own reasoning.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Self-Modeling</h3>
          <p className="text-sm text-muted-foreground">The platform understands its own capabilities and limitations, enabling intelligent task routing.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Cognitive Modules</h3>
          <p className="text-sm text-muted-foreground">Pluggable cognitive architecture — attention, memory, reasoning, planning, and perception modules.</p>
        </div>
      </div>
    </AppShell>
  );
}
