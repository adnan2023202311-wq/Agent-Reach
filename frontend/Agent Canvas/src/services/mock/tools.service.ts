import { toolsData, type Tool } from "@/features/tools/data";
import type { ToolsService } from "@/services/types";

export const toolsMockService: ToolsService = {
  list: async () => toolsData,
  listSync: () => toolsData,
  update: async (id: string, patch: Partial<Tool>) => {
    const idx = toolsData.findIndex((t) => t.id === id);
    if (idx === -1) throw new Error(`Tool "${id}" not found`);
    const next = { ...toolsData[idx], ...patch };
    toolsData[idx] = next;
    return next;
  },
};
