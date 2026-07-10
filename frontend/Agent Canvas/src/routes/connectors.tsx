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

export const Route = createFileRoute("/connectors")({
  component: ConnectorsPage,
  head: () => ({ meta: [{ title: "Connectors · Agent Reach Studio" }, { name: "description", content: "Universal connector framework." }] }),
});

function ConnectorsPage() {
  const onNavigate = useAppNavigation("connectors");
  const topbar = useTopbar();
  const [catalog, setCatalog] = React.useState<any>(null);
  const [connectors, setConnectors] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    Promise.all([
      api.get<any>("/api/v1/connectors/v2/catalog").catch(() => ({})),
      api.get<any>("/api/v1/connectors/v2").catch(() => ({ connectors: [] })),
    ]).then(([c, con]) => { setCatalog(c); setConnectors(con.connectors || []); }).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="connectors" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.17" title="Universal Connectors" description="Native connectors for GitHub, GitLab, Jira, Slack, Discord, Notion, AWS, Azure, GCP, and more." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading connectors…</div>
      ) : (
        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-semibold mb-3">Available Connector Types ({catalog?.count ?? 0})</h2>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {Object.entries(catalog?.connectors || {}).map(([id, info]: [string, any]) => (
                <Card key={id}>
                  <CardHeader><CardTitle className="text-sm">{info.name}</CardTitle></CardHeader>
                  <CardContent><div className="text-xs text-muted-foreground">{info.capabilities?.length || 0} capabilities · Auth: {info.auth_type}</div></CardContent>
                </Card>
              ))}
            </div>
          </div>
          <div>
            <h2 className="text-sm font-semibold mb-3">Configured Connectors ({connectors.length})</h2>
            {connectors.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2">{connectors.map((c: any) => (<Card key={c.connector_id}><CardHeader><CardTitle className="text-sm">{c.name}</CardTitle></CardHeader><CardContent><Badge variant={c.configured ? "success" : "warning"}>{c.configured ? "Configured" : "Pending"}</Badge></CardContent></Card>))}</div>
            ) : (<div className="text-sm text-muted-foreground">No connectors configured yet.</div>)}
          </div>
        </div>
      )}
    </AppShell>
  );
}
