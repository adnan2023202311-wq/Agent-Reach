import {
  activityStats,
  recentChats,
  activeAgents,
  dashboardTools,
} from "@/features/dashboard/data";
import type { DashboardService, DashboardSnapshot } from "@/services/types";

function snapshot(): DashboardSnapshot {
  return {
    activity: activityStats,
    recentChats,
    activeAgents,
    tools: dashboardTools,
  };
}

export const dashboardMockService: DashboardService = {
  snapshot: async () => snapshot(),
  snapshotSync: () => snapshot(),
  activitySync: () => activityStats,
  recentChatsSync: () => recentChats,
  activeAgentsSync: () => activeAgents,
  toolsSync: () => dashboardTools,
};
