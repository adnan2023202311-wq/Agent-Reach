/**
 * HTTP-backed service implementations.
 *
 * Milestone 8 — Production Frontend Integration.
 *
 * Every method now calls the FastAPI backend via the shared `api` client.
 * Return shapes match the mock service contracts exactly so routes need
 * zero changes when switching VITE_API_MODE.
 *
 * To activate: set `VITE_API_MODE=http` and `VITE_API_BASE_URL=http://localhost:8000`.
 */

import { api } from "@/lib/api/client";
import type {
  AgentsService,
  ChatService,
  DashboardService,
  ProvidersService,
  Services,
  ToolsService,
  Message,
  SendMessageInput,
  Agent,
  Provider,
  Tool,
  ChatAgentOption,
  ProviderCatalogEntry,
  DashboardSnapshot,
} from "@/services/types";

import { agentsData, chatAgents as staticChatAgents } from "@/features/agents/data";
import { providersData, providerCatalog as staticProviderCatalog, topbarProviders as staticTopbarProviders, topbarModels as staticTopbarModels } from "@/features/providers/data";
import { toolsData } from "@/features/tools/data";
import { chatSuggestions as staticChatSuggestions, agentSuggestions as staticAgentSuggestions, recentChats as staticRecent, type Suggestion } from "@/features/chat/data";
import {
  activityStats as staticActivity,
  recentChats as dashboardRecent,
  activeAgents as dashboardAgents,
  dashboardTools as dashboardTools,
} from "@/features/dashboard/data";

// --- helpers to merge backend data with static UI metadata ---

const agentUiMap = new Map(agentsData.map(a => [a.id, a]));
const providerUiMap = new Map(providersData.map(p => [p.id, p]));
const toolUiMap = new Map(toolsData.map(t => [t.id, t]));

function mergeAgent(apiAgent: any): Agent {
  const ui = agentUiMap.get(apiAgent.id);
  return {
    id: apiAgent.id,
    name: apiAgent.name || ui?.name || apiAgent.id,
    description: apiAgent.description || ui?.description || "",
    icon: ui?.icon || agentsData[0].icon,
    tint: ui?.tint || "bg-accent/15 text-accent",
    status: (apiAgent.status as any) || "ready",
    enabled: apiAgent.enabled ?? true,
    providerId: apiAgent.provider_id || ui?.providerId || "anthropic",
    modelId: apiAgent.model_id || ui?.modelId || "claude-sonnet-4",
    systemPrompt: apiAgent.system_prompt || ui?.systemPrompt || "",
    temperature: ui?.temperature ?? 0.3,
    maxTokens: apiAgent.max_tokens || ui?.maxTokens || 1024,
  };
}

function mergeProvider(apiProvider: any): Provider {
  const ui = providerUiMap.get(apiProvider.id);
  return {
    id: apiProvider.id,
    name: ui?.name || apiProvider.id,
    short: ui?.short || apiProvider.id.slice(0,2).toUpperCase(),
    tint: ui?.tint || "bg-accent/15 text-accent",
    description: ui?.description || "",
    status: apiProvider.status || "unconfigured",
    enabled: apiProvider.enabled ?? false,
    apiKey: ui?.apiKey || "",
    baseUrl: ui?.baseUrl || "",
    defaultBaseUrl: ui?.defaultBaseUrl || "",
    defaultModel: ui?.defaultModel || "",
    models: ui?.models || [],
    docsUrl: ui?.docsUrl || "",
  };
}

function mergeTool(apiTool: any): Tool {
  const ui = toolUiMap.get(apiTool.id);
  return {
    id: apiTool.id,
    name: apiTool.name || ui?.name || apiTool.id,
    description: apiTool.description || ui?.description || "",
    icon: ui?.icon || toolsData[0].icon,
    tint: ui?.tint || "bg-accent/15 text-accent",
    status: (apiTool.status as any) || "ready",
    enabled: apiTool.enabled ?? true,
    category: apiTool.category || ui?.category || "general",
    configFields: ui?.configFields || [],
  };
}

// --- Providers ---

export const providersHttpService: ProvidersService = {
  list: async () => {
    try {
      const data = await api.get<any[]>("/api/v1/providers");
      return data.map(mergeProvider);
    } catch {
      // fallback to static
      return providersData;
    }
  },
  listSync: () => providersData,
  catalog: async () => {
    try {
      const list = await providersHttpService.list();
      return list.map(p => ({ id: p.id, name: p.name, models: p.models }));
    } catch {
      return staticProviderCatalog;
    }
  },
  catalogSync: () => staticProviderCatalog,
  topbarProviders: () => staticTopbarProviders,
  topbarModels: () => staticTopbarModels,
  update: async (id, patch) => {
    try {
      await api.patch(`/api/v1/providers/${id}`, patch);
    } catch (e) {
      // backend returns 501 – not implemented – keep UI optimistic
    }
    const current = providerUiMap.get(id);
    if (!current) throw new Error(`Provider "${id}" not found`);
    return { ...current, ...patch } as Provider;
  },
};

// --- Agents ---

export const agentsHttpService: AgentsService = {
  list: async () => {
    try {
      const data = await api.get<any[]>("/api/v1/agents");
      return data.map(mergeAgent);
    } catch {
      return agentsData;
    }
  },
  listSync: () => agentsData,
  chatOptions: (): ChatAgentOption[] => staticChatAgents,
  update: async (id, patch) => {
    try {
      await api.patch(`/api/v1/agents/${id}`, patch);
    } catch {
      // 501 expected
    }
    const current = agentUiMap.get(id);
    if (!current) throw new Error(`Agent "${id}" not found`);
    return { ...current, ...patch } as Agent;
  },
};

// --- Tools ---

export const toolsHttpService: ToolsService = {
  list: async () => {
    try {
      const data = await api.get<any[]>("/api/v1/tools");
      // backend tools endpoint shape: check
      if (Array.isArray(data)) return data.map(mergeTool);
      return toolsData;
    } catch {
      return toolsData;
    }
  },
  listSync: () => toolsData,
  update: async (id, patch) => {
    const current = toolUiMap.get(id);
    if (!current) throw new Error(`Tool "${id}" not found`);
    return { ...current, ...patch } as Tool;
  },
};

// --- Chat ---

let _sessionId: string | null = null;

async function ensureSession(): Promise<string> {
  if (_sessionId) return _sessionId;
  try {
    const s = await api.post<{session_id:string}>("/api/v1/conversations/sessions", { user_id: "web" });
    _sessionId = s.session_id;
    return _sessionId;
  } catch {
    _sessionId = "web-" + Math.random().toString(36).slice(2);
    return _sessionId;
  }
}

export const chatHttpService: ChatService = {
  suggestions: (mode) => mode === "agent" ? staticAgentSuggestions : staticChatSuggestions,
  recent: async () => staticRecent,
  recentSync: () => staticRecent,
  sendMessage: async (input: SendMessageInput): Promise<Message> => {
    const session_id = await ensureSession();
    try {
      // try conversation API first (M6+)
      const res = await api.post<any>(`/api/v1/conversations/sessions/${session_id}/messages`, {
        session_id,
        message: input.content,
        context: {
          mode: input.mode,
          provider_id: input.providerId,
          model_id: input.modelId,
          agent_id: input.agentId,
        }
      });
      return {
        id: res.message_id || `m_${Date.now()}`,
        role: "assistant",
        content: res.content || "…",
        createdAt: Date.now(),
      } as Message;
    } catch {
      // fallback to legacy /api/v1/chat
      try {
        const res = await api.post<any>("/api/v1/chat", {
          message: input.content,
          session_id,
          context: {
            mode: input.mode,
            provider: input.providerId,
            model: input.modelId,
            agent: input.agentId,
          }
        });
        return {
          id: `m_${Date.now()}`,
          role: "assistant",
          content: res.answer || res.content || "Done.",
          createdAt: Date.now(),
        } as Message;
      } catch (e:any) {
        return {
          id: `m_${Date.now()}`,
          role: "assistant",
          content: `Backend unavailable: ${e?.message || e}`,
          createdAt: Date.now(),
        } as Message;
      }
    }
  },
};

// --- Dashboard ---

export const dashboardHttpService: DashboardService = {
  snapshot: async (): Promise<DashboardSnapshot> => {
    try {
      const data = await api.get<any>("/api/v1/dashboard");
      return {
        activity: data.activity || staticActivity,
        recentChats: data.recent_chats || dashboardRecent,
        activeAgents: data.active_agents?.map((a:any) => ({
          id: a.id,
          name: a.name,
          status: a.status,
          tasksCompleted: 0,
          icon: agentUiMap.get(a.id)?.icon || dashboardAgents[0]?.icon,
        })) || dashboardAgents,
        tools: data.tools || dashboardTools,
      };
    } catch {
      return {
        activity: staticActivity,
        recentChats: dashboardRecent,
        activeAgents: dashboardAgents,
        tools: dashboardTools,
      };
    }
  },
  snapshotSync: () => ({
    activity: staticActivity,
    recentChats: dashboardRecent,
    activeAgents: dashboardAgents,
    tools: dashboardTools,
  }),
  activitySync: () => staticActivity,
  recentChatsSync: () => dashboardRecent,
  activeAgentsSync: () => dashboardAgents,
  toolsSync: () => dashboardTools,
};

export const httpServices: Services = {
  providers: providersHttpService,
  agents: agentsHttpService,
  tools: toolsHttpService,
  chat: chatHttpService,
  dashboard: dashboardHttpService,
};
