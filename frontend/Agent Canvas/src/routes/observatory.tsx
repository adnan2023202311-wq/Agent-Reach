import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import { api } from "@/lib/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
export const Route = createFileRoute("/observatory")({ component: ObservatoryPage });
function ObservatoryPage(){
  const onNavigate = useAppNavigation("observatory");
  const topbar = useTopbar();
  const [data,setData] = React.useState<any>({});
  const load = React.useCallback(()=>{ api.get("/api/v1/observatory/live").then(setData).catch(()=>{}); },[]);
  React.useEffect(()=>{ load(); const id=setInterval(load,3000); return ()=>clearInterval(id); },[load]);
  const subs = data.integration?.subsystems || {};
  return (<AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="observatory" onNavigate={onNavigate}>
    <PageHeader eyebrow="Live" title="Execution Observatory" description="Real-time Pipeline — /api/v1/observatory/live" />
    <div className="grid gap-3 md:grid-cols-4">
      {Object.entries(subs).map(([k,v]:any)=>(<Card key={k}><CardHeader><CardTitle className="text-xs uppercase">{k}</CardTitle></CardHeader><CardContent><div className="text-lg font-mono">{v.active?"● LIVE":"○"}</div><div className="text-[10px] text-muted-foreground">{v.type||"-"}</div></CardContent></Card>))}
    </div>
    <Card className="mt-4"><CardHeader><CardTitle className="text-sm">Trace</CardTitle></CardHeader><CardContent><pre className="text-[10px] overflow-auto max-h-96">{JSON.stringify(data,null,2)}</pre></CardContent></Card>
  </AppShell>);
}
