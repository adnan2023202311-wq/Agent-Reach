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

export const Route = createFileRoute("/billing")({
  component: BillingPage,
  head: () => ({ meta: [{ title: "Billing · Agent Reach Studio" }, { name: "description", content: "Billing & resource management." }] }),
});

function BillingPage() {
  const onNavigate = useAppNavigation("billing");
  const topbar = useTopbar();
  const [summary, setSummary] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api.get<any>("/api/v1/billing/usage/summary").then(setSummary).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="billing" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.15" title="Billing & Resource Management" description="Usage tracking, credits, quotas, and cost optimization." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading billing data…</div>
      ) : summary ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card><CardHeader><CardTitle className="text-sm">Total Requests</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{summary.total_requests ?? 0}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Total Cost</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">${summary.total_cost?.toFixed(4) ?? "0.00"}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Tokens In</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{summary.total_tokens_in ?? 0}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Tokens Out</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{summary.total_tokens_out ?? 0}</div></CardContent></Card>
        </div>
      ) : (<div className="text-sm text-muted-foreground">Billing data unavailable.</div>)}
    </AppShell>
  );
}
