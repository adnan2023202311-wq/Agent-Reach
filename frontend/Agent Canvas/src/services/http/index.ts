/**
 * HTTP-backed service implementations.
 *
 * These are scaffolds — every method currently throws `NotImplementedError`.
 * When the FastAPI backend is ready, fill each method by calling the shared
 * `api` client (see `src/lib/api/client.ts`). The mock service files are the
 * behavioural spec: match their return shapes exactly.
 *
 * To activate: set `VITE_API_MODE=http` and `VITE_API_BASE_URL=...`.
 */

import type {
  AgentsService,
  ChatService,
  DashboardService,
  ProvidersService,
  Services,
  ToolsService,
} from "@/services/types";

class NotImplementedError extends Error {
  constructor(fn: string) {
    super(`${fn} is not implemented yet — set VITE_API_MODE=mock or implement the HTTP call.`);
    this.name = "NotImplementedError";
  }
}

const todo =
  (name: string) =>
  async (): Promise<never> => {
    throw new NotImplementedError(name);
  };
const todoSync = (name: string) => (): never => {
  throw new NotImplementedError(name);
};

export const providersHttpService: ProvidersService = {
  list: todo("providers.list"),
  listSync: todoSync("providers.listSync"),
  catalog: todo("providers.catalog"),
  catalogSync: todoSync("providers.catalogSync"),
  topbarProviders: todoSync("providers.topbarProviders"),
  topbarModels: todoSync("providers.topbarModels"),
  update: todo("providers.update"),
};

export const agentsHttpService: AgentsService = {
  list: todo("agents.list"),
  listSync: todoSync("agents.listSync"),
  chatOptions: todoSync("agents.chatOptions"),
  update: todo("agents.update"),
};

export const toolsHttpService: ToolsService = {
  list: todo("tools.list"),
  listSync: todoSync("tools.listSync"),
  update: todo("tools.update"),
};

export const chatHttpService: ChatService = {
  suggestions: todoSync("chat.suggestions"),
  recent: todo("chat.recent"),
  recentSync: todoSync("chat.recentSync"),
  sendMessage: todo("chat.sendMessage"),
};

export const dashboardHttpService: DashboardService = {
  snapshot: todo("dashboard.snapshot"),
  snapshotSync: todoSync("dashboard.snapshotSync"),
  activitySync: todoSync("dashboard.activitySync"),
  recentChatsSync: todoSync("dashboard.recentChatsSync"),
  activeAgentsSync: todoSync("dashboard.activeAgentsSync"),
  toolsSync: todoSync("dashboard.toolsSync"),
};

export const httpServices: Services = {
  providers: providersHttpService,
  agents: agentsHttpService,
  tools: toolsHttpService,
  chat: chatHttpService,
  dashboard: dashboardHttpService,
};
