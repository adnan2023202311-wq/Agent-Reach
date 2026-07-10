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

export const Route = createFileRoute("/infrastructure")({
  component: InfrastructurePage,
  head: () => ({ meta: [{ title: "Infrastructure · Agent Reach Studio" }, { name: "description", content: "Autonomous infrastructure manager." }] }),
});

function InfrastructurePage() {
  const onNavigate = useAppNavigation("infrastructure");
  const topbar = useTopbar();
  const [status, setStatus] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api.get<any>("/api/v1/infrastructure/status").then(setStatus).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="infrastructure" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.16" title="Autonomous Infrastructure Manager" description="Scaling, recovery, deployment, resource allocation, and optimization." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading infrastructure status…</div>
      ) : status ? (
        <div className="grid gap-4 md:grid-cols-3">
          <Card><CardHeader><CardTitle className="text-sm">Cluster Nodes</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{status.cluster?.total_nodes ?? 0}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Active Deployments</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{status.active_deployments ?? 0}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Scaling Policies</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{status.scaling_policies ?? 0}</div></CardContent></Card>
        </div>
      ) : (<div className="text-sm text-muted-foreground">Infrastructure data unavailable.</div>)}
    </AppShell>
  );
}
