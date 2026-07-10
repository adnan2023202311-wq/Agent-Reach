import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import { api } from "@/lib/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/common/spinner";

export const Route = createFileRoute("/monitoring")({
  component: MonitoringPage,
  head: () => ({
    meta: [
      { title: "Monitoring · Agent Reach Studio" },
      { name: "description", content: "Production monitoring center." },
    ],
  }),
});

function MonitoringPage() {
  const onNavigate = useAppNavigation("monitoring");
  const topbar = useTopbar();
  const [dashboard, setDashboard] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api.get<any>("/api/v1/monitoring/dashboard").then(setDashboard).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="monitoring" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.13" title="Production Monitoring" description="Centralized monitoring of agents, workflows, costs, latency, and errors." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading monitoring data…</div>
      ) : dashboard ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card><CardHeader><CardTitle className="text-sm">Total Requests</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{dashboard.requests?.total ?? 0}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Success Rate</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold text-success">{((dashboard.requests?.success_rate ?? 0) * 100).toFixed(1)}%</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Avg Latency</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{Math.round(dashboard.requests?.avg_latency_ms ?? 0)}ms</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Active Sessions</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{dashboard.sessions?.active ?? 0}</div></CardContent></Card>
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">Monitoring data unavailable. Is the backend running?</div>
      )}
    </AppShell>
  );
}
