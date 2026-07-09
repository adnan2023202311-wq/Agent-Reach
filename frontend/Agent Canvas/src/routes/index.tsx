import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  MessagesSquare,
  Plus,
  Play,
  KeyRound,
  Settings as SettingsIcon,
  ArrowRight,
  type LucideIcon,
} from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { StatusIndicator } from "@/components/common/status-indicator";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { tileToneClass } from "@/lib/status";

import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import { dashboardService, type ActivityStat } from "@/services";

// Static catalog data for the initial paint — these have real LucideIcon
// components. The backend returns trace summaries (no icons), so aggregate
// counters always stay sourced from the catalog.
const activityStatsFallback = dashboardService.activitySync();
const recentChatsFallback = dashboardService.recentChatsSync();
const activeAgentsFallback = dashboardService.activeAgentsSync();
const dashboardToolsFallback = dashboardService.toolsSync();


export const Route = createFileRoute("/")({
  component: DashboardPage,
  head: () => ({
    meta: [
      { title: "Dashboard · Agent Reach Studio" },
      {
        name: "description",
        content:
          "A quick overview of your workspace — today's activity, recent chats, active agents and tools.",
      },
      { property: "og:title", content: "Dashboard · Agent Reach Studio" },
      { property: "og:description", content: "Your AI workspace at a glance." },
    ],
  }),
});

// ---------------------------------------------------------------------------
// ErrorBoundary — catches any render crash so the user sees a message
// instead of a blank white screen.
// ---------------------------------------------------------------------------
class DashboardErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; message: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, message: "" };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error.message };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 text-center">
          <h2 className="text-lg font-semibold text-destructive">Dashboard render error</h2>
          <pre className="mt-2 text-xs text-muted-foreground">{this.state.message}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}


function DashboardPage() {
  const onNavigate = useAppNavigation("dashboard");
  const topbar = useTopbar();

  const [agents, setAgents] = React.useState(activeAgentsFallback);

  React.useEffect(() => {
    let mounted = true;
    dashboardService.snapshot().then((snap) => {
      if (!mounted) return;
      if (snap.activeAgents?.length) setAgents(snap.activeAgents as any);
    }).catch(() => {});
    return () => { mounted = false; };
  }, []);

  return (
    <AppShell
      {...topbar}
      sidebarItems={defaultSidebarItems}
      activeSidebarId="dashboard"
      onNavigate={onNavigate}
    >
      <DashboardErrorBoundary>
        <DashboardContent
          onNavigate={onNavigate}
          agents={agents}
        />
      </DashboardErrorBoundary>
    </AppShell>
  );
}


function DashboardContent({
  onNavigate,
  agents,
}: {
  onNavigate: (id: string) => void;
  agents: any[];
}) {
  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description="A snapshot of your workspace — today's activity, agents, tools and shortcuts."
        actions={
          <Button variant="accent" size="sm" onClick={() => onNavigate("chat")}>
            <Plus size={14} />
            New chat
          </Button>
        }
      />

      <div className="space-y-8">
        {/* ----- Activity ----- */}
        <section aria-labelledby="section-activity" className="space-y-3">
          <SectionHeader id="section-activity" title="Today's activity" />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {activityStatsFallback.map((s) => (
              <StatCard key={s.id} stat={s} />
            ))}
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* ----- Recent chats ----- */}
          <section aria-labelledby="section-chats" className="space-y-3 lg:col-span-2">
            <SectionHeader
              id="section-chats"
              title="Recent chats"
              action={
                <Button variant="ghost" size="sm" onClick={() => onNavigate("chat")}>
                  Open chat
                  <ArrowRight size={13} />
                </Button>
              }
            />
            <SafeCard>
              <ul className="divide-y divide-border">
                {recentChatsFallback.map((chat) => (
                  <li key={chat.id}>
                    <button
                      type="button"
                      onClick={() => onNavigate("chat")}
                      className="w-full flex items-start gap-3 p-4 text-left transition-colors hover:bg-surface-hover focus-visible:outline-none focus-visible:bg-surface-hover"
                    >
                      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
                        <MessagesSquare size={15} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between gap-3">
                          <div className="text-sm font-medium text-foreground truncate">{chat.title}</div>
                          <div className="text-[11px] text-muted-foreground shrink-0 font-mono">{chat.updatedAt}</div>
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">{chat.snippet}</p>
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <Badge variant="subtle" className="text-[10px]">{chat.provider}</Badge>
                          <Badge variant="outline" className="text-[10px] font-mono">{chat.model}</Badge>
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </SafeCard>
          </section>

          {/* ----- Quick actions ----- */}
          <section aria-labelledby="section-actions" className="space-y-3">
            <SectionHeader id="section-actions" title="Quick actions" />
            <SafeCard>
              <div className="grid grid-cols-2 gap-2 p-3">
                <QuickAction icon={Plus} label="New chat" onClick={() => onNavigate("chat")} />
                <QuickAction icon={Play} label="Run agent" onClick={() => onNavigate("agents")} />
                <QuickAction icon={KeyRound} label="Configure provider" onClick={() => onNavigate("settings")} />
                <QuickAction icon={SettingsIcon} label="Configure tool" onClick={() => onNavigate("tools")} />
              </div>
            </SafeCard>
          </section>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* ----- Active agents ----- */}
          <section aria-labelledby="section-agents" className="space-y-3">
            <SectionHeader
              id="section-agents"
              title="Active agents"
              action={
                <Button variant="ghost" size="sm" onClick={() => onNavigate("agents")}>
                  Manage
                  <ArrowRight size={13} />
                </Button>
              }
            />
            <SafeCard>
              <ul className="divide-y divide-border">
                {agents.map((agent: any) => {
                  const Icon = agent.icon;
                  if (!Icon) return null;
                  return (
                    <li key={agent.id} className="flex items-center gap-3 p-3.5">
                      <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg border border-border", agent.tint)}>
                        <Icon size={15} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-foreground truncate">{agent.name}</div>
                        <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                          <span>{agent.provider}</span>
                          <span aria-hidden>·</span>
                          <span className="font-mono truncate">{agent.model}</span>
                        </div>
                      </div>
                      <StatusIndicator tone="success" label="Enabled" pulse />
                    </li>
                  );
                })}
              </ul>
            </SafeCard>
          </section>

          {/* ----- Tools status ----- */}
          <section aria-labelledby="section-tools" className="space-y-3">
            <SectionHeader
              id="section-tools"
              title="Tools status"
              action={
                <Button variant="ghost" size="sm" onClick={() => onNavigate("tools")}>
                  Manage
                  <ArrowRight size={13} />
                </Button>
              }
            />
            <SafeCard>
              <ul className="divide-y divide-border">
                {dashboardToolsFallback.map((tool: any) => {
                  const Icon = tool.icon;
                  if (!Icon) return null;
                  return (
                    <li key={tool.id} className="flex items-center gap-3 p-3.5">
                      <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg border border-border", tileToneClass(tool.statusTone === "success" ? "accent" : tool.statusTone))}>
                        <Icon size={15} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-foreground truncate">{tool.name}</div>
                        <div className="mt-0.5 text-[11px] text-muted-foreground truncate">{tool.detail}</div>
                      </div>
                      <StatusIndicator tone={tool.statusTone} label={tool.statusLabel} pulse={tool.statusTone === "success"} />
                    </li>
                  );
                })}
              </ul>
            </SafeCard>
          </section>
        </div>
      </div>
    </>
  );
}


// =========================================================================
// Helpers
// =========================================================================

function SectionHeader({ id, title, action }: { id: string; title: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <h2 id={id} className="text-sm font-semibold tracking-tight text-foreground">{title}</h2>
      {action}
    </div>
  );
}

function StatCard({ stat }: { stat: ActivityStat }) {
  const Icon = (stat as any)?.icon;
  if (typeof Icon !== "function") return null;

  const toneMap: Record<string, string> = {
    accent: "bg-accent/15 text-accent",
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    destructive: "bg-destructive/15 text-destructive",
  };
  const tone = toneMap[(stat as any).tone] ?? "";

  const label = (stat as any).label ?? "";
  const value = (stat as any).value ?? 0;
  const delta = (stat as any).delta ?? "";

  // Render with SafeCard so the chunk-load race during hydration
  // never crashes — SafeCard falls back to a plain <div> when the
  // shadcn Card chunk hasn't loaded yet.
  return (
    <SafeCard>
      <div className="flex flex-col space-y-1.5 p-6 flex-row items-center justify-between pb-2">
        <div className="font-semibold leading-none tracking-tight text-xs uppercase tracking-wider text-muted-foreground font-medium">
          {label}
        </div>
        <div className={cn("flex size-8 items-center justify-center rounded-lg", tone)}>
          <Icon size={14} />
        </div>
      </div>
      <div className="p-6 pt-0">
        <div className="text-2xl font-semibold tracking-tight text-foreground tabular-nums">
          {value}
        </div>
        <div className="text-sm text-muted-foreground mt-0.5 text-[11px]">{delta}</div>
      </div>
    </SafeCard>
  );
}

function SafeCard({ children }: { children: React.ReactNode }) {
  // Wrapper that renders a plain div when the shadcn Card chunk
  // hasn't loaded yet during client-side hydration. All Dashboard
  // components that need a card container MUST go through SafeCard.
  try {
    if (typeof Card === "function") {
      return <Card>{children}</Card>;
    }
  } catch { /* hydration race — fall through */ }
  return <div className="rounded-xl border bg-card text-card-foreground shadow">{children}</div>;
}

function QuickAction({ icon: Icon, label, onClick }: { icon: LucideIcon; label: string; onClick: () => void }) {
  if (typeof Icon !== "function") return null;
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col items-start gap-2 rounded-lg border border-border bg-surface p-3 text-left transition-colors hover:bg-surface-hover hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <div className="flex size-8 items-center justify-center rounded-md bg-surface-hover text-muted-foreground group-hover:text-accent transition-colors">
        <Icon size={14} />
      </div>
      <div className="text-xs font-medium text-foreground leading-tight">{label}</div>
    </button>
  );
}
