import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import { api } from "@/lib/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Spinner } from "@/components/common/spinner";

export const Route = createFileRoute("/marketplace")({ component: MarketplacePage });

function MarketplacePage() {
  const onNavigate = useAppNavigation("marketplace");
  const topbar = useTopbar();
  const [items, setItems] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  const refresh = () => {
    setLoading(true);
    api.get<any>("/api/v1/marketplace/plugins")
      .then((d: any) => setItems(d.items || []))
      .catch((e: any) => toast.error(e?.message || "Failed to load marketplace"))
      .finally(() => setLoading(false));
  };

  React.useEffect(() => { refresh(); }, []);

  const install = async (pluginId: string) => {
    if (!pluginId) { toast.error("Missing plugin ID"); return; }
    try {
      const payload = { plugin_id: pluginId };
      await api.post("/api/v1/marketplace/plugins/install", payload);
      toast.success(`Installed ${pluginId}`);
      refresh();
    } catch (e: any) {
      toast.error(e?.message || "Install failed");
    }
  };

  const uninstall = async (pluginId: string) => {
    if (!pluginId) { toast.error("Missing plugin ID"); return; }
    try {
      await api.delete(`/api/v1/marketplace/plugins/${pluginId}`);
      toast.success(`Uninstalled ${pluginId}`);
      refresh();
    } catch (e: any) {
      toast.error(e?.message || "Uninstall failed");
    }
  };

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="marketplace" onNavigate={onNavigate}>
      <PageHeader eyebrow="Ecosystem" title="Plugin Marketplace" description="Install verified plugins — /api/v1/marketplace" />
      {loading && items.length === 0 ? (
        <div className="flex items-center gap-3 p-8 text-muted-foreground"><Spinner /> Loading marketplace…</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {items.map((p: any) => {
            const pid = p.plugin_id || "";
            const installed = p.status === "installed";
            return (
              <Card key={pid || Math.random()}>
                <CardHeader>
                  <CardTitle className="text-sm">{p.name || pid}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-xs text-muted-foreground mb-2">v{p.version || "1.0.0"} · {p.author || "AgentReach"}</div>
                  <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{p.description || ""}</p>
                  <div className="flex items-center justify-between">
                    <Badge variant={installed ? "success" : "secondary"}>
                      {installed ? "installed" : "available"}
                    </Badge>
                    {installed ? (
                      <Button size="sm" variant="outline" onClick={() => uninstall(pid)}>Uninstall</Button>
                    ) : (
                      <Button size="sm" variant="accent" onClick={() => install(pid)}>Install</Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
