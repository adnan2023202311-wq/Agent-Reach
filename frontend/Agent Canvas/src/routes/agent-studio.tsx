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
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
export const Route = createFileRoute("/agent-studio")({ component: AgentStudioPage });
function AgentStudioPage(){
  const onNavigate = useAppNavigation("agent-studio");
  const topbar = useTopbar();
  const [name,setName]=React.useState("My Agent");
  const [prompt,setPrompt]=React.useState("You are a helpful assistant.");
  const [catalog,setCatalog]=React.useState<any>({catalog:[],drafts:[]});
  React.useEffect(()=>{ api.get("/api/v1/studio/agents").then(setCatalog).catch(()=>{}); },[]);
  const save = async()=>{ const r = await api.post("/api/v1/studio/agents/draft",{name, description:"", system_prompt:prompt, tools:[], model_provider:"anthropic", model_id:"claude-sonnet-4", temperature:0.3, max_tokens:2048, memory_enabled:true, reasoning:"balanced"}); toast.success(`Draft saved: ${r.id}`); };
  const test = async()=>{ const id = name.toLowerCase().replace(/\s+/g,"_"); const r = await api.post(`/api/v1/studio/agents/${id}/test`,{prompt:"Hello"}); toast(r.output); };
  return (<AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="agent-studio" onNavigate={onNavigate}>
    <PageHeader eyebrow="Builder" title="Agent Studio" description="No-code agent builder — /api/v1/studio/agents" />
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader><CardTitle className="text-sm">Create Agent</CardTitle></CardHeader><CardContent className="space-y-3">
        <Input value={name} onChange={e=>setName(e.target.value)} placeholder="Agent name" />
        <Textarea rows={6} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="System prompt" />
        <div className="flex gap-2"><Button onClick={save} variant="accent" size="sm">Save Draft</Button><Button onClick={test} variant="outline" size="sm">Test</Button></div>
      </CardContent></Card>
      <Card><CardHeader><CardTitle className="text-sm">Catalog</CardTitle></CardHeader><CardContent>
        <ul className="text-xs space-y1">{catalog.catalog?.map((a:any)=>(<li key={a.id}>{a.name} — {a.status}</li>))}</ul>
        <div className="text-[11px] text-muted-foreground mt-3">Drafts: {catalog.drafts?.length||0}</div>
      </CardContent></Card>
    </div>
  </AppShell>);
}
