import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion } from "framer-motion";
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

const activityStats = dashboardService.activitySync();
const recentChats = dashboardService.recentChatsSync();
const activeAgents = dashboardService.activeAgentsSync();
const dashboardTools = dashboardService.toolsSync();


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

function DashboardPage() {
  const onNavigate = useAppNavigation("dashboard");
  const topbar = useTopbar();

  return (
    <AppShell
      {...topbar}
      sidebarItems={defaultSidebarItems}
      activeSidebarId="dashboard"
      onNavigate={onNavigate}
    >

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

      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="space-y-8"
      >
        <section aria-labelledby="section-activity" className="space-y-3">
          <SectionHeader id="section-activity" title="Today's activity" />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {activityStats.map((s) => (
              <StatCard key={s.id} stat={s} />
            ))}
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
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
            <Card>
              <ul className="divide-y divide-border">
                {recentChats.map((chat) => (
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
                          <div className="text-sm font-medium text-foreground truncate">
                            {chat.title}
                          </div>
                          <div className="text-[11px] text-muted-foreground shrink-0 font-mono">
                            {chat.updatedAt}
                          </div>
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">
                          {chat.snippet}
                        </p>
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <Badge variant="subtle" className="text-[10px]">
                            {chat.provider}
                          </Badge>
                          <Badge variant="outline" className="text-[10px] font-mono">
                            {chat.model}
                          </Badge>
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          </section>

          <section aria-labelledby="section-actions" className="space-y-3">
            <SectionHeader id="section-actions" title="Quick actions" />
            <Card>
              <CardContent className="grid grid-cols-2 gap-2 p-3">
                <QuickAction icon={Plus} label="New chat" onClick={() => onNavigate("chat")} />
                <QuickAction icon={Play} label="Run agent" onClick={() => onNavigate("agents")} />
                <QuickAction
                  icon={KeyRound}
                  label="Configure provider"
                  onClick={() => onNavigate("settings")}
                />
                <QuickAction
                  icon={SettingsIcon}
                  label="Configure tool"
                  onClick={() => onNavigate("tools")}
                />
              </CardContent>
            </Card>
          </section>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
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
            <Card>
              <ul className="divide-y divide-border">
                {activeAgents.map((agent) => {
                  const Icon = agent.icon;
                  return (
                    <li key={agent.id} className="flex items-center gap-3 p-3.5">
                      <div
                        className={cn(
                          "flex size-9 shrink-0 items-center justify-center rounded-lg border border-border",
                          agent.tint,
                        )}
                      >
                        <Icon size={15} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-foreground truncate">
                          {agent.name}
                        </div>
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
            </Card>
          </section>

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
            <Card>
              <ul className="divide-y divide-border">
                {dashboardTools.map((tool) => {
                  const Icon = tool.icon;
                  return (
                    <li key={tool.id} className="flex items-center gap-3 p-3.5">
                      <div
                        className={cn(
                          "flex size-9 shrink-0 items-center justify-center rounded-lg border border-border",
                          tileToneClass(tool.statusTone === "success" ? "accent" : tool.statusTone),
                        )}
                      >
                        <Icon size={15} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-foreground truncate">
                          {tool.name}
                        </div>
                        <div className="mt-0.5 text-[11px] text-muted-foreground truncate">
                          {tool.detail}
                        </div>
                      </div>
                      <StatusIndicator
                        tone={tool.statusTone}
                        label={tool.statusLabel}
                        pulse={tool.statusTone === "success"}
                      />
                    </li>
                  );
                })}
              </ul>
            </Card>
          </section>
        </div>
      </motion.div>
    </AppShell>
  );
}

function SectionHeader({
  id,
  title,
  action,
}: {
  id: string;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <h2 id={id} className="text-sm font-semibold tracking-tight text-foreground">
        {title}
      </h2>
      {action}
    </div>
  );
}

function StatCard({ stat }: { stat: ActivityStat }) {
  const Icon = stat.icon;
  const tone = {
    accent: "bg-accent/15 text-accent",
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    destructive: "bg-destructive/15 text-destructive",
  }[stat.tone];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground font-medium">
          {stat.label}
        </CardTitle>
        <div className={cn("flex size-8 items-center justify-center rounded-lg", tone)}>
          <Icon size={14} />
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold tracking-tight text-foreground tabular-nums">
          {stat.value}
        </div>
        <CardDescription className="mt-0.5 text-[11px]">{stat.delta}</CardDescription>
      </CardContent>
    </Card>
  );
}

function QuickAction({
  icon: Icon,
  label,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
}) {
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
