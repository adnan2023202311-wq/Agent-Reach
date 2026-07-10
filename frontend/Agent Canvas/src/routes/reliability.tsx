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

export const Route = createFileRoute("/reliability")({
  component: ReliabilityPage,
  head: () => ({ meta: [{ title: "Reliability · Agent Reach Studio" }, { name: "description", content: "Production reliability." }] }),
});

function ReliabilityPage() {
  const onNavigate = useAppNavigation("reliability");
  const topbar = useTopbar();
  const [health, setHealth] = React.useState<any[]>([]);
  const [sla, setSla] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    Promise.all([
      api.get<any[]>("/api/v1/reliability/health").catch(() => []),
      api.get<any>("/api/v1/reliability/sla").catch(() => null),
    ]).then(([h, s]) => { setHealth(h); setSla(s); }).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="reliability" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.31" title="Production Reliability" description="Health checks, circuit breakers, rate limiting, and SLA monitoring." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading reliability data…</div>
      ) : (
        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-semibold mb-3">Health Checks</h2>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {health.map((h: any) => (
                <Card key={h.check_id}><CardHeader><CardTitle className="text-sm flex items-center justify-between">{h.name} <span className={h.healthy ? "text-success" : "text-destructive"}>{h.healthy ? "●" : "○"}</span></CardTitle></CardHeader><CardContent><div className="text-xs text-muted-foreground">{h.message || (h.healthy ? "Healthy" : "Unhealthy")}</div></CardContent></Card>
              ))}
            </div>
          </div>
          {sla && (
            <div>
              <h2 className="text-sm font-semibold mb-3">SLA Metrics</h2>
              <div className="grid gap-3 md:grid-cols-3">
                {sla.metrics?.map((m: any) => (
                  <Card key={m.metric_name}><CardHeader><CardTitle className="text-sm">{m.metric_name}</CardTitle></CardHeader><CardContent><div className="text-lg font-bold">{m.actual}{m.unit}</div><div className="text-xs text-muted-foreground">Target: {m.target}{m.unit}</div></CardContent></Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
