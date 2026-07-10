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

export const Route = createFileRoute("/distributed")({
  component: DistributedPage,
  head: () => ({
    meta: [
      { title: "Distributed Cloud · Agent Reach Studio" },
      { name: "description", content: "Cluster nodes and agent swarms." },
    ],
  }),
});

function DistributedPage() {
  const onNavigate = useAppNavigation("distributed");
  const topbar = useTopbar();
  const [nodes, setNodes] = React.useState<any[]>([]);
  const [swarms, setSwarms] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  const refresh = React.useCallback(() => {
    setLoading(true);
    Promise.all([
      api.get<any>("/api/v1/distributed/nodes").catch(() => ({ nodes: [] })),
      api.get<any>("/api/v1/distributed/swarm").catch(() => ({ swarms: [] })),
    ]).then(([nodesResp, swarmsResp]) => {
      setNodes(nodesResp.nodes || []);
      setSwarms(swarmsResp.swarms || []);
    }).finally(() => setLoading(false));
  }, []);

  React.useEffect(() => { refresh(); }, [refresh]);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="distributed" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.1 + M10.2" title="Distributed Agent Cloud" description="Cluster nodes, remote agents, and swarm intelligence." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading cluster state…</div>
      ) : (
        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-semibold mb-3">Cluster Nodes ({nodes.length})</h2>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {nodes.map((n: any) => (
                <Card key={n.node_id}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm">{n.hostname}</CardTitle>
                      <Badge variant={n.status === "online" ? "success" : "destructive"}>{n.status}</Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="text-xs text-muted-foreground space-y-1">
                      <div>ID: <span className="font-mono">{n.node_id.slice(0, 12)}…</span></div>
                      <div>Endpoint: <span className="font-mono">{n.endpoint}</span></div>
                      <div>Load: {n.current_load}/{n.max_concurrent}</div>
                      <div>Capabilities: {n.capabilities.join(", ") || "—"}</div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
          <div>
            <h2 className="text-sm font-semibold mb-3">Recent Swarms ({swarms.length})</h2>
            <div className="grid gap-3 md:grid-cols-2">
              {swarms.map((s: any) => (
                <Card key={s.swarm_id}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm truncate">{s.objective}</CardTitle>
                      <Badge variant={s.consensus_reached ? "success" : "warning"}>
                        {s.consensus_reached ? "Consensus" : "Split"}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="text-xs text-muted-foreground space-y-1">
                      <div>Winner: {s.winning_role || "—"}</div>
                      <div>Members: {s.member_count}</div>
                      <div>Status: {s.status}</div>
                    </div>
                  </CardContent>
                </Card>
              ))}
              {swarms.length === 0 && (
                <div className="text-sm text-muted-foreground">No swarms executed yet.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
