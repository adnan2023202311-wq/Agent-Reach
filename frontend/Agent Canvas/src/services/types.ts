/**
 * Service interfaces — one per domain.
 *
 * Every route in the app talks to the domain through these interfaces,
 * NOT through the mock data modules under `@/features/<domain>/data`. That lets us
 * swap the mock implementation for an HTTP-backed one without touching any
 * route file. See `src/services/index.ts` for the current binding.
 *
 * Each interface exposes:
 *   - async methods (`list`, `get`, mutations) that match the future HTTP shape
 *   - sync accessors (`*Sync`) so routes can initialize `useState` from the
 *     mock without an initial loading flash today. When the HTTP backend
 *     lands, routes migrate to the async methods via TanStack Query.
 */

import type {
  Provider,
  ProviderCatalogEntry,
  ProviderStatus,
} from "@/features/providers/data";
import type { Agent, AgentStatus, ChatAgentOption } from "@/features/agents/data";
import type { Tool, ToolStatus, ConfigField } from "@/features/tools/data";
import type { Message, Suggestion, ChatMode, RecentChat } from "@/features/chat/data";
import type {
  ActivityStat,
  ActiveAgentSummary,
  DashboardTool,
} from "@/features/dashboard/data";
import type {
  ProviderOption,
  ModelOption,
} from "@/components/layout/provider-selector";

// Re-export the domain types so consumers only import from `@/services/*`.
export type {
  Provider,
  ProviderCatalogEntry,
  ProviderStatus,
  Agent,
  AgentStatus,
  ChatAgentOption,
  Tool,
  ToolStatus,
  ConfigField,
  Message,
  Suggestion,
  ChatMode,
  RecentChat,
  ActivityStat,
  ActiveAgentSummary,
  DashboardTool,
  ProviderOption,
  ModelOption,
};

// ---------------------------------------------------------------------------
// Providers
// ---------------------------------------------------------------------------

export interface ProvidersService {
  list(): Promise<Provider[]>;
  listSync(): Provider[];
  catalog(): Promise<ProviderCatalogEntry[]>;
  catalogSync(): ProviderCatalogEntry[];
  topbarProviders(): ProviderOption[];
  topbarModels(): ModelOption[];
  update(id: string, patch: Partial<Provider>): Promise<Provider>;
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export interface AgentsService {
  list(): Promise<Agent[]>;
  listSync(): Agent[];
  chatOptions(): ChatAgentOption[];
  update(id: string, patch: Partial<Agent>): Promise<Agent>;
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

export interface ToolsService {
  list(): Promise<Tool[]>;
  listSync(): Tool[];
  update(id: string, patch: Partial<Tool>): Promise<Tool>;
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface SendMessageInput {
  content: string;
  mode: ChatMode;
  providerId: string;
  modelId: string;
  agentId?: string;
}

export interface ChatService {
  suggestions(mode: ChatMode): Suggestion[];
  recent(): Promise<RecentChat[]>;
  recentSync(): RecentChat[];
  /** Mock reply generator — returns an assistant message for a given input. */
  sendMessage(input: SendMessageInput): Promise<Message>;
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export interface DashboardSnapshot {
  activity: ActivityStat[];
  recentChats: RecentChat[];
  activeAgents: ActiveAgentSummary[];
  tools: DashboardTool[];
}

export interface DashboardService {
  snapshot(): Promise<DashboardSnapshot>;
  snapshotSync(): DashboardSnapshot;
  activitySync(): ActivityStat[];
  recentChatsSync(): RecentChat[];
  activeAgentsSync(): ActiveAgentSummary[];
  toolsSync(): DashboardTool[];
}

// ---------------------------------------------------------------------------
// Root services registry
// ---------------------------------------------------------------------------

export interface Services {
  providers: ProvidersService;
  agents: AgentsService;
  tools: ToolsService;
  chat: ChatService;
  dashboard: DashboardService;
}
