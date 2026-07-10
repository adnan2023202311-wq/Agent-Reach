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

export const Route = createFileRoute("/enterprise")({
  component: EnterprisePage,
  head: () => ({
    meta: [
      { title: "Enterprise · Agent Reach Studio" },
      { name: "description", content: "Organizations, teams, RBAC, and compliance." },
    ],
  }),
});

function EnterprisePage() {
  const onNavigate = useAppNavigation("enterprise");
  const topbar = useTopbar();
  const [orgs, setOrgs] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api.get<any>("/api/v1/enterprise/orgs")
      .then((d: any) => setOrgs(d.orgs || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="enterprise" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.7" title="Enterprise Platform" description="Organizations, teams, RBAC, audit logs, and compliance." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading organizations…</div>
      ) : orgs.length === 0 ? (
        <div className="text-sm text-muted-foreground">No organizations created yet. Use POST /api/v1/enterprise/orgs to create one.</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {orgs.map((org: any) => (
            <Card key={org.org_id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">{org.name}</CardTitle>
                  <Badge variant="secondary">{org.tier}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground space-y-1">
                  <div>ID: <span className="font-mono">{org.org_id.slice(0, 12)}…</span></div>
                  <div>Max users: {org.max_users}</div>
                  <div>Features: {org.features.join(", ") || "—"}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}
