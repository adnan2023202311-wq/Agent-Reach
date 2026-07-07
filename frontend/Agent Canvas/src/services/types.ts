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
// Milestone 8 — Extended Workspace Services
// ---------------------------------------------------------------------------

export interface MemoryItem { id: string; content: string; importance: number; }
export interface MemoryService {
  stats(): Promise<any>;
  search(query: string, count?: number): Promise<MemoryItem[]>;
  store(content: string, importance?: number): Promise<{id:string}>;
  working(): Promise<MemoryItem[]>;
  compress(): Promise<any>;
  clear(): Promise<void>;
}

export interface KnowledgeNode { id: string; label: string; type: string; }
export interface KnowledgeEdge { source: string; target: string; type: string; }
export interface KnowledgeService {
  stats(): Promise<any>;
  search(query: string): Promise<any[]>;
  graph(limit?: number): Promise<{nodes: KnowledgeNode[]; edges: KnowledgeEdge[]}>;
  upload(file: File, collection?: string): Promise<any>;
  clear(): Promise<void>;
}

export interface PromptRecord { name: string; version: number; template: string; variables?: string[]; }
export interface PromptsService {
  list(search?: string): Promise<PromptRecord[]>;
  get(name: string, version?: number): Promise<PromptRecord>;
  create(input: {name:string; template:string; variables?:string[]}): Promise<any>;
  test(template: string, variables: Record<string,any>): Promise<{rendered:string}>;
  history(name: string): Promise<any[]>;
  optimize(name: string): Promise<any>;
}

export interface WorkflowSummary { id: string; name: string; description?: string; status?: string; }
export interface WorkflowsService {
  list(): Promise<WorkflowSummary[]>;
  get(id: string): Promise<any>;
  run(id: string, input?: any): Promise<any>;
  validate(graph: any): Promise<any>;
}

export interface ObservatoryService {
  live(): Promise<any>;
  metrics(): Promise<any>;
  trace(requestId: string): Promise<any>;
}

export interface SkillsService {
  list(category?: string): Promise<any[]>;
  get(id: string): Promise<any>;
  execute(id: string, input: any): Promise<any>;
}

export interface MarketplaceService {
  list(): Promise<any[]>;
  install(pluginId: string, version?: string): Promise<any>;
  uninstall(pluginId: string): Promise<any>;
}

export interface PlaygroundService {
  models(): Promise<any>;
  compare(prompt: string, providers: string[]): Promise<any>;
}

export interface ConnectorsService {
  list(): Promise<any[]>;
  get(id: string): Promise<any>;
  test(id: string): Promise<any>;
}

export interface CollaborationService {
  organizations(): Promise<any[]>;
  teams(): Promise<any[]>;
  audit(limit?: number): Promise<any[]>;
}

export interface AgentStudioService {
  list(): Promise<any>;
  draft(input: any): Promise<any>;
  test(agentId: string, prompt: string): Promise<any>;
  publish(agentId: string): Promise<any>;
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
  // M8
  memory?: MemoryService;
  knowledge?: KnowledgeService;
  prompts?: PromptsService;
  workflows?: WorkflowsService;
  observatory?: ObservatoryService;
  skills?: SkillsService;
  marketplace?: MarketplaceService;
  playground?: PlaygroundService;
  connectors?: ConnectorsService;
  collaboration?: CollaborationService;
  agentStudio?: AgentStudioService;
}
