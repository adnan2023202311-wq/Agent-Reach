import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import { api } from "@/lib/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/knowledge")({ component: KnowledgePage });

function KnowledgePage(){
  const onNavigate = useAppNavigation("knowledge");
  const topbar = useTopbar();
  const [q,setQ] = React.useState(""); const [results,setResults] = React.useState<any[]>([]);
  const [graph,setGraph] = React.useState<any>({nodes:[],edges:[]});
  React.useEffect(()=>{ api.get("/api/v1/knowledge/graph?limit=50").then(setGraph).catch(()=>{}); },[]);
  const search = async()=>{ try{ const r = await api.post("/api/v1/knowledge/search",{query:q,limit:20}); setResults(r.results||[]);}catch{} };
  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="knowledge" onNavigate={onNavigate}>
      <PageHeader eyebrow="RAG Studio" title="Knowledge & RAG Studio" description="Knowledge Graph + Vector Search — /api/v1/knowledge" />
      <div className="flex gap-2 mb-4"><Input placeholder="Search knowledge…" value={q} onChange={e=>setQ(e.target.value)} onKeyDown={e=>e.key==="Enter"&&search()} /><Button onClick={search} variant="accent">Search</Button></div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle className="text-sm">Graph — {graph.nodes?.length||0} nodes / {graph.edges?.length||0} edges</CardTitle></CardHeader><CardContent><pre className="text-[10px] max-h-80 overflow-auto">{JSON.stringify(graph,null,2)}</pre></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-sm">Search Results — {results.length}</CardTitle></CardHeader><CardContent><ul className="text-xs space-y-2">{results.map((r:any,i:number)=><li key={i} className="border-b border-border pb-2">{r.label||r.id||JSON.stringify(r)}</li>)}{results.length===0&&<li className="text-muted-foreground">No results — try search above</li>}</ul></CardContent></Card>
      </div>
    </AppShell>
  );
}
