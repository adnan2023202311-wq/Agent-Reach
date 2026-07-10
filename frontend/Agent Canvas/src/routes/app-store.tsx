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

export const Route = createFileRoute("/app-store")({
  component: AppStorePage,
  head: () => ({ meta: [{ title: "App Store · Agent Reach Studio" }, { name: "description", content: "AI App Store." }] }),
});

function AppStorePage() {
  const onNavigate = useAppNavigation("app-store");
  const topbar = useTopbar();
  const [apps, setApps] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api.get<any>("/api/v1/app-store/apps").then((d) => setApps(d.apps || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="app-store" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.19" title="AI App Store" description="Discover, install, and publish AI applications. Ratings, reviews, and revenue sharing." />
      {loading ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading app store…</div>
      ) : apps.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {apps.map((a: any) => (
            <Card key={a.app_id}>
              <CardHeader><CardTitle className="text-sm">{a.name}</CardTitle></CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground mb-2">{a.description}</div>
                <div className="flex items-center justify-between text-xs">
                  <span>⭐ {a.rating.toFixed(1)} ({a.rating_count})</span>
                  <span>{a.price === 0 ? "Free" : `$${a.price}`}</span>
                  <span>{a.install_count} installs</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (<div className="text-sm text-muted-foreground">No apps published yet.</div>)}
    </AppShell>
  );
}
