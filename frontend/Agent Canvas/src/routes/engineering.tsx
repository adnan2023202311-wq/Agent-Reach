import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";

export const Route = createFileRoute("/engineering")({
  component: EngineeringPage,
  head: () => ({ meta: [{ title: "Engineering · Agent Reach Studio" }, { name: "description", content: "AI engineering platform." }] }),
});

function EngineeringPage() {
  const onNavigate = useAppNavigation("engineering");
  const topbar = useTopbar();

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="engineering" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.32 + M10.33" title="AI Engineering Platform" description="Code review, refactoring, architecture analysis, test generation, and documentation generation." />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Code Review</h3>
          <p className="text-sm text-muted-foreground">Automated static analysis with security, design, and maintainability findings. Score: 0-100.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Refactoring Plans</h3>
          <p className="text-sm text-muted-foreground">Extract method, rename, simplify, deduplicate, and modernize — each with step-by-step plans and risk assessment.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Test Generation</h3>
          <p className="text-sm text-muted-foreground">Automatically generate unit tests from source code. Extract functions and classes, generate test stubs.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Documentation Generation</h3>
          <p className="text-sm text-muted-foreground">Generate markdown documentation for modules, functions, classes, and APIs from source code.</p>
        </div>
      </div>
    </AppShell>
  );
}
