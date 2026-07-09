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
import { Play } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/workflows")({
  component: WorkflowsPage,
});

function WorkflowsPage() {
  const onNavigate = useAppNavigation("workflows");
  const topbar = useTopbar();
  const [items, setItems] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api.get<any[]>("/api/v1/workflows").then((d) => Array.isArray(d) ? setItems(d) : setItems([])).catch(()=> setItems([])).finally(()=>setLoading(false));
  }, []);

  // Fallback demo workflows when API is empty
  const display = items.length ? items : [
    { id: "research_pipeline", name: "Research Pipeline", description: "Multi-agent research with synthesis", status: "ready" },
    { id: "code_review", name: "Code Review", description: "Automated PR analysis", status: "ready" },
    { id: "content_gen", name: "Content Generation", description: "Blog post + social threads", status: "draft" },
  ];

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="workflows" onNavigate={onNavigate}>
      <PageHeader eyebrow="Studio" title="Visual Workflow Studio" description="Drag-and-drop workflow editor — backend API ready (M8.3)." />
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {display.map((w:any)=>(
          <Card key={w.id}>
            <CardHeader><CardTitle className="text-sm">{w.name || w.id}</CardTitle></CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">{w.description || "M8 Visual Workflow"}</p>
              <div className="flex items-center justify-between">
                <Badge variant="success">{w.status || "ready"}</Badge>
                <Button size="sm" variant="accent" onClick={()=>toast(`Run ${w.id} — POST /api/v1/workflows/${w.id}/run`)}><Play size={13}/> Run</Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      {loading && <p className="text-xs text-muted-foreground mt-4">Loading from /api/v1/workflows …</p>}
    </AppShell>
  );
}
