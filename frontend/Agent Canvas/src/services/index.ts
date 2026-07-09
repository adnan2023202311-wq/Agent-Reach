/**
 * Services registry — the single import surface for domain data.
 *
 * Routes and components import `services` from here (never from
 * `@/features/<domain>/data` directly). Switching from mock to HTTP requires only
 * flipping `VITE_API_MODE` to `"http"`; no route changes.
 *
 * Individual service objects are also re-exported for convenient destructuring.
 */

import type { Services } from "./types";

import { providersMockService } from "./mock/providers.service";
import { agentsMockService } from "./mock/agents.service";
import { toolsMockService } from "./mock/tools.service";
import { chatMockService } from "./mock/chat.service";
import { dashboardMockService } from "./mock/dashboard.service";

import { httpServices } from "./http";

type ApiMode = "mock" | "http";
const MODE: ApiMode =
  (import.meta.env.VITE_API_MODE as ApiMode | undefined) === "mock" ? "mock" : "http";

const mockServices: Services = {
  providers: providersMockService,
  agents: agentsMockService,
  tools: toolsMockService,
  chat: chatMockService,
  dashboard: dashboardMockService,
};

export const services: Services = MODE === "http" ? httpServices : mockServices;

export const {
  providers: providersService,
  agents: agentsService,
  tools: toolsService,
  chat: chatService,
  dashboard: dashboardService,
} = services;

// Re-export domain constants that live alongside the mock data but are UI
// contracts (limits, enums) rather than fetched values.
export { CHAT_MAX_CHARS } from "@/features/chat/data";
export { AGENT_STATUS_META } from "@/features/agents/data";
export { TOOL_STATUS_META } from "@/features/tools/data";

export * from "./types";
