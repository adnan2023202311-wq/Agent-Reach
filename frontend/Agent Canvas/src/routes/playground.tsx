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
export const Route = createFileRoute("/playground")({ component: PlaygroundPage });
function PlaygroundPage(){
  const onNavigate = useAppNavigation("playground");
  const topbar = useTopbar();
  const [prompt,setPrompt]=React.useState("Compare: What is Agent Reach?");
  const [results,setResults]=React.useState<any[]>([]);
  const run = async()=>{ const r: any = await api.post<any>("/api/v1/playground/compare",{prompt, providers:["anthropic","openai","google"]}); setResults(r.results||[]); };
  return (<AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="playground" onNavigate={onNavigate}>
    <PageHeader eyebrow="Model Lab" title="Model Playground" description="Side-by-side multi-provider — /api/v1/playground" />
    <Card className="mb-4"><CardContent className="p-4 space-y-3"><Textarea value={prompt} onChange={e=>setPrompt(e.target.value)} rows={3}/><Button onClick={run} variant="accent">Compare Models</Button></CardContent></Card>
    <div className="grid gap-4 md:grid-cols-3">{results.map((r:any)=>(<Card key={r.provider}><CardHeader><CardTitle className="text-sm">{r.provider}</CardTitle></CardHeader><CardContent className="text-xs space-y1"><div>latency: {r.latency_ms}ms</div><div>cost: ${r.cost_usd}</div><div>quality: {r.quality_score}</div><p className="mt-2 text-[11px]">{r.output}</p></CardContent></Card>))}</div>
  </AppShell>);
}
