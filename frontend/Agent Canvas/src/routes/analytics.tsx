import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import { api } from "@/lib/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/common/spinner";

export const Route = createFileRoute("/analytics")({
  component: AnalyticsPage,
  head: () => ({ meta: [{ title: "Analytics · Agent Reach Studio" }, { name: "description", content: "Advanced analytics." }] }),
});

function AnalyticsPage() {
  const onNavigate = useAppNavigation("analytics");
  const topbar = useTopbar();
  const [overview, setOverview] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api.get<any>("/api/v1/analytics/overview").then(setOverview).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="analytics" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.36" title="Advanced Analytics" description="Cross-subsystem metrics, trends, and automated insights." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading analytics…</div>
      ) : overview ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card><CardHeader><CardTitle className="text-sm">Executions</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{overview.execution?.total ?? 0}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Success Rate</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold text-success">{((overview.execution?.success_rate ?? 0) * 100).toFixed(1)}%</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Avg Latency</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{Math.round(overview.performance?.avg_latency_ms ?? 0)}ms</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Active Providers</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{overview.providers?.active_count ?? 0}</div></CardContent></Card>
        </div>
      ) : (<div className="text-sm text-muted-foreground">Analytics data unavailable.</div>)}
    </AppShell>
  );
}
