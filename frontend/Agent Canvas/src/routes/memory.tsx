import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import { api } from "@/lib/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const Route = createFileRoute("/memory")({ component: MemoryPage });

function MemoryPage(){
  const onNavigate = useAppNavigation("memory");
  const topbar = useTopbar();
  const [stats,setStats] = React.useState<any>({});
  const [working,setWorking] = React.useState<any[]>([]);
  React.useEffect(()=>{ api.get("/api/v1/memory/stats").then(setStats).catch(()=>{}); api.get("/api/v1/memory/working").then((d:any)=>setWorking(d.items||[])).catch(()=>{}); },[]);
  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="memory" onNavigate={onNavigate}>
      <PageHeader eyebrow="Intelligence" title="LongCat Memory Studio" description="Hierarchical memory — M7.1 / M8.2 — live via /api/v1/memory" />
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardHeader><CardTitle className="text-sm">Working Memory</CardTitle></CardHeader><CardContent><div className="text-2xl font-semibold">{stats.working_size ?? working.length ?? 0}</div></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-sm">Long-Term</CardTitle></CardHeader><CardContent><div className="text-2xl font-semibold">{stats.long_term_count ?? "—"}</div></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-sm">Engine</CardTitle></CardHeader><CardContent><div className="text-sm">{stats.engine || "LongCat"}</div></CardContent></Card>
      </div>
      <Card className="mt-6"><CardHeader><CardTitle className="text-sm">Working Snapshot</CardTitle></CardHeader><CardContent><pre className="text-xs overflow-auto max-h-96">{JSON.stringify(working, null, 2)}</pre></CardContent></Card>
    </AppShell>
  );
}
