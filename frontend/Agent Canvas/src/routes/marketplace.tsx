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
export const Route = createFileRoute("/marketplace")({ component: MarketplacePage });
function MarketplacePage(){
  const onNavigate = useAppNavigation("marketplace");
  const topbar = useTopbar();
  const [items,setItems] = React.useState<any[]>([]);
  React.useEffect(()=>{ api.get("/api/v1/marketplace/plugins").then((d:any)=>setItems(d.items||[])).catch(()=>{}); },[]);
  return (<AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="marketplace" onNavigate={onNavigate}>
    <PageHeader eyebrow="Ecosystem" title="Plugin Marketplace" description="Install verified plugins — /api/v1/marketplace" />
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {items.map((p:any)=>(<Card key={p.id}><CardHeader><CardTitle className="text-sm">{p.name}</CardTitle></CardHeader><CardContent>
        <div className="text-xs text-muted-foreground mb-2">v{p.version} · {p.author} · ⭐ {p.rating}</div>
        <div className="flex items-center justify-between"><Badge variant={p.verified?"success":"secondary"}>{p.verified?"verified":"community"}</Badge>
        <Button size="sm" variant="accent" onClick={()=>api.post("/api/v1/marketplace/plugins/install",{plugin_id:p.id})}>Install</Button></div>
      </CardContent></Card>))}
      {items.length===0&&<Card><CardContent className="p-6 text-sm text-muted-foreground">Loading marketplace…</CardContent></Card>}
    </div>
  </AppShell>);
}
