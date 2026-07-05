/**
 * Dashboard mocks — the dashboard is a *view* over the other feature domains,
 * so almost everything here is derived from the source-of-truth data in the
 * chat, agents, providers and tools modules. The only dashboard-owned mocks
 * are the aggregate counters ("today's activity") and the per-tool usage
 * annotations, both of which a real backend would compute separately.
 */

import { MessagesSquare, Bot, Wrench, AlertTriangle, type LucideIcon } from "lucide-react";
import type { StatusTone } from "@/lib/status";
import { agentsData, AGENT_STATUS_META } from "@/features/agents/data";
import { providerCatalog } from "@/features/providers/data";
import { toolsData, TOOL_STATUS_META, type ToolStatus } from "@/features/tools/data";
import { recentChats } from "@/features/chat/data";

// Re-export so dashboard consumers can pull everything from one module.
export { recentChats };
export type { RecentChat } from "@/features/chat/data";

// ---------------------------------------------------------------------------
// Today's activity (dashboard-owned aggregate counters)
// ---------------------------------------------------------------------------

export interface ActivityStat {
  id: string;
  label: string;
  value: number;
  delta: string;
  tone: "accent" | "success" | "warning" | "destructive";
  icon: LucideIcon;
}

export const activityStats: ActivityStat[] = [
  { id: "chats", label: "Chats", value: 24, delta: "+6 today", tone: "accent", icon: MessagesSquare },
  { id: "runs", label: "Agent runs", value: 12, delta: "+3 today", tone: "success", icon: Bot },
  { id: "tools", label: "Tool executions", value: 87, delta: "+21 today", tone: "warning", icon: Wrench },
  { id: "errors", label: "Errors", value: 2, delta: "-4 vs yesterday", tone: "destructive", icon: AlertTriangle },
];

// ---------------------------------------------------------------------------
// Active agents (derived from the agents feature)
// ---------------------------------------------------------------------------

export interface ActiveAgentSummary {
  id: string;
  name: string;
  provider: string;
  model: string;
  icon: LucideIcon;
  tint: string;
  statusLabel: string;
  statusTone: StatusTone;
}

export const activeAgents: ActiveAgentSummary[] = agentsData
  .filter((a) => a.enabled)
  .map((a) => {
    const provider = providerCatalog.find((p) => p.id === a.providerId);
    const modelName = provider?.models.find((m) => m.id === a.modelId)?.name ?? a.modelId;
    const meta = AGENT_STATUS_META[a.status];
    return {
      id: a.id,
      name: a.name,
      provider: provider?.name ?? a.providerId,
      model: modelName,
      icon: a.icon,
      tint: a.tint,
      statusLabel: meta.label,
      statusTone: meta.tone,
    };
  });

// ---------------------------------------------------------------------------
// Tools status snapshot (derived from the tools feature)
//
// Dashboard-only overlay: per-tool usage detail. Everything else — id, name,
// icon, status — comes from the shared tools module.
// ---------------------------------------------------------------------------

const TOOL_USAGE_DETAIL: Record<string, string> = {
  browser: "12 calls today",
  search: "34 calls today",
  http: "41 calls today",
  rss: "Add feed URLs",
  telegram: "Missing bot token",
  filesystem: "Root path unreachable",
};

export interface DashboardTool {
  id: string;
  name: string;
  icon: LucideIcon;
  status: ToolStatus;
  statusLabel: string;
  statusTone: StatusTone;
  detail: string;
}

export const dashboardTools: DashboardTool[] = toolsData.map((t) => {
  const meta = TOOL_STATUS_META[t.status];
  return {
    id: t.id,
    name: t.name,
    icon: t.icon,
    status: t.status,
    statusLabel: meta.label,
    statusTone: meta.tone,
    detail: TOOL_USAGE_DETAIL[t.id] ?? meta.label,
  };
});
