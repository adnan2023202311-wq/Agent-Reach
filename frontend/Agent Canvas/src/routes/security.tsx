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

export const Route = createFileRoute("/security")({
  component: SecurityPage,
  head: () => ({
    meta: [{ title: "Security · Agent Reach Studio" }, { name: "description", content: "AI Security Center." }],
  }),
});

function SecurityPage() {
  const onNavigate = useAppNavigation("security");
  const topbar = useTopbar();
  const [scan, setScan] = React.useState<any>(null);
  const [secrets, setSecrets] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    Promise.all([
      api.get<any>("/api/v1/security/scan").catch(() => ({})),
      api.get<any>("/api/v1/security/secrets").catch(() => ({ secrets: [] })),
    ]).then(([s, sec]) => { setScan(s); setSecrets(sec.secrets || []); }).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="security" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.14" title="AI Security Center" description="Secrets management, threat detection, vulnerability scanning, and policy enforcement." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading security data…</div>
      ) : (
        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle className="text-sm">Vulnerability Scan</CardTitle></CardHeader>
            <CardContent>
              {scan?.findings?.length > 0 ? (
                <div className="space-y-2">
                  {scan.findings.map((f: any, i: number) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <Badge variant={f.severity === "high" ? "destructive" : "warning"}>{f.severity}</Badge>
                      <span>{f.description}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-success">No vulnerabilities found. ✅</div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">Stored Secrets ({secrets.length})</CardTitle></CardHeader>
            <CardContent>
              {secrets.length > 0 ? (
                <div className="space-y-2">{secrets.map((s: any) => (<div key={s.secret_id} className="text-sm flex items-center justify-between"><span>{s.name}</span><Badge variant="secondary">{s.type}</Badge></div>))}</div>
              ) : (<div className="text-sm text-muted-foreground">No secrets stored. Use POST /api/v1/security/secrets to add one.</div>)}
            </CardContent>
          </Card>
        </div>
      )}
    </AppShell>
  );
}
