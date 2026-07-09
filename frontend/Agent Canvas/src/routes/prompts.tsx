import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import { api } from "@/lib/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
export const Route = createFileRoute("/prompts")({ component: PromptsPage });
function PromptsPage(){
  const onNavigate = useAppNavigation("prompts");
  const topbar = useTopbar();
  const [list,setList] = React.useState<any[]>([]);
  const [tpl,setTpl] = React.useState("You are {{role}}. Task: {{task}}");
  const [vars,setVars] = React.useState('{"role":"researcher","task":"summarize"}');
  const [out,setOut] = React.useState("");
  React.useEffect(()=>{ api.get<any>("/api/v1/prompts").then((d:any)=>setList(d.items||[])).catch(()=>{}); },[]);
  const test = async()=>{ try{ const v = JSON.parse(vars); const r: any = await api.post<any>("/api/v1/prompts/test",{template:tpl,variables:v}); setOut(r.rendered);}catch(e:any){ setOut(e.message);} };
  return (<AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="prompts" onNavigate={onNavigate}>
    <PageHeader eyebrow="Prompt Intelligence" title="Prompt Studio" description="Versioning, testing, optimization — /api/v1/prompts" />
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader><CardTitle className="text-sm">Test Prompt</CardTitle></CardHeader><CardContent className="space-y-3">
        <Textarea rows={5} value={tpl} onChange={e=>setTpl(e.target.value)} />
        <Input value={vars} onChange={e=>setVars(e.target.value)} placeholder='{"var":"value"}' className="font-mono text-xs" />
        <Button onClick={test} variant="accent" size="sm">Render</Button>
        {out && <pre className="text-xs bg-surface p-2 rounded border">{out}</pre>}
      </CardContent></Card>
      <Card><CardHeader><CardTitle className="text-sm">Library — {list.length}</CardTitle></CardHeader><CardContent><ul className="text-xs space-y-1">{list.map((p:any,i:number)=><li key={i}>{p.name} v{p.version}</li>)}{list.length===0&&<li className="text-muted-foreground">Empty — create via API POST /api/v1/prompts</li>}</ul></CardContent></Card>
    </div>
  </AppShell>);
}
