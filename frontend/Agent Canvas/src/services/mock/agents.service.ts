import { agentsData, chatAgents, type Agent } from "@/features/agents/data";
import type { AgentsService } from "@/services/types";

export const agentsMockService: AgentsService = {
  list: async () => agentsData,
  listSync: () => agentsData,
  chatOptions: () => chatAgents,
  update: async (id: string, patch: Partial<Agent>) => {
    const idx = agentsData.findIndex((a) => a.id === id);
    if (idx === -1) throw new Error(`Agent "${id}" not found`);
    const next = { ...agentsData[idx], ...patch };
    agentsData[idx] = next;
    return next;
  },
};
