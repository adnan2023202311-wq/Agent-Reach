/**
 * Provider domain — the vendors we can talk to and how the app displays them.
 *
 * `Provider` is the full, editable record (owned by the Providers settings
 * page). The topbar's lightweight `ProviderOption` / `ModelOption` selectors
 * live in `@/components/layout/provider-selector`; helpers to derive them
 * from this data live at the bottom of the file.
 *
 * When the FastAPI backend arrives, `providersData` will be replaced by a
 * `useQuery` hook that fetches the same shape — nothing else needs to change.
 */

import type { LucideIcon } from "lucide-react";
import type { ProviderOption, ModelOption } from "@/components/layout/provider-selector";

export type ProviderStatus = "ready" | "unconfigured" | "error";

export interface ProviderModel {
  id: string;
  name: string;
}

export interface Provider {
  id: string;
  name: string;
  /** 2-letter mark used in place of a vendor SVG logo. */
  short: string;
  /** Tailwind class pair for the logo tile background + foreground. */
  tint: string;
  description: string;
  status: ProviderStatus;
  enabled: boolean;
  apiKey: string;
  baseUrl: string;
  defaultBaseUrl: string;
  defaultModel: string;
  models: ProviderModel[];
  docsUrl: string;
}

/** Minimal provider record consumed by the agent config sheet. */
export interface ProviderCatalogEntry {
  id: string;
  name: string;
  models: ProviderModel[];
}

/** Icon slot for future rich provider cards — currently unused, kept for extension. */
export type ProviderIcon = LucideIcon;

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

export const providersData: Provider[] = [
  {
    id: "openai",
    name: "OpenAI",
    short: "AI",
    tint: "bg-[#10a37f]/15 text-[#10a37f]",
    description: "GPT-5, GPT-4o, o-series reasoning models.",
    status: "unconfigured",
    enabled: false,
    apiKey: "",
    baseUrl: "",
    defaultBaseUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-5",
    models: [
      { id: "gpt-5", name: "GPT-5" },
      { id: "gpt-4o", name: "GPT-4o" },
      { id: "o4-mini", name: "o4-mini" },
    ],
    docsUrl: "https://platform.openai.com/docs",
  },
  {
    id: "anthropic",
    name: "Anthropic",
    short: "AN",
    tint: "bg-[#d97757]/15 text-[#d97757]",
    description: "Claude Sonnet, Opus and Haiku model family.",
    status: "ready",
    enabled: true,
    apiKey: "sk-ant-••••••••••••••••7f2a",
    baseUrl: "",
    defaultBaseUrl: "https://api.anthropic.com",
    defaultModel: "claude-sonnet-4",
    models: [
      { id: "claude-opus-4", name: "Claude Opus 4" },
      { id: "claude-sonnet-4", name: "Claude Sonnet 4" },
      { id: "claude-haiku-4", name: "Claude Haiku 4" },
    ],
    docsUrl: "https://docs.anthropic.com",
  },
  {
    id: "google",
    name: "Google",
    short: "GO",
    tint: "bg-[#4285f4]/15 text-[#4285f4]",
    description: "Gemini 2.5 Pro and Flash multimodal models.",
    status: "ready",
    enabled: true,
    apiKey: "AIza••••••••••••••••••wq",
    baseUrl: "",
    defaultBaseUrl: "https://generativelanguage.googleapis.com/v1",
    defaultModel: "gemini-2.5-pro",
    models: [
      { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro" },
      { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash" },
    ],
    docsUrl: "https://ai.google.dev/docs",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    short: "OR",
    tint: "bg-[#a855f7]/15 text-[#a855f7]",
    description: "Unified access to hundreds of models via one key.",
    status: "ready",
    enabled: true,
    apiKey: "sk-or-••••••••••••••••ab19",
    baseUrl: "",
    defaultBaseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "anthropic/claude-sonnet-4",
    models: [
      { id: "anthropic/claude-sonnet-4", name: "anthropic/claude-sonnet-4" },
      { id: "openai/gpt-5", name: "openai/gpt-5" },
      { id: "google/gemini-2.5-pro", name: "google/gemini-2.5-pro" },
    ],
    docsUrl: "https://openrouter.ai/docs",
  },
  {
    id: "groq",
    name: "Groq",
    short: "GQ",
    tint: "bg-[#f55036]/15 text-[#f55036]",
    description: "Ultra-low-latency LPU inference for open models.",
    status: "error",
    enabled: true,
    apiKey: "gsk_••••••••••••••••dead",
    baseUrl: "",
    defaultBaseUrl: "https://api.groq.com/openai/v1",
    defaultModel: "llama-3.3-70b",
    models: [
      { id: "llama-3.3-70b", name: "Llama 3.3 70B" },
      { id: "mixtral-8x22b", name: "Mixtral 8x22B" },
    ],
    docsUrl: "https://console.groq.com/docs",
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    short: "DS",
    tint: "bg-[#4d6bfe]/15 text-[#4d6bfe]",
    description: "DeepSeek-V3 chat and DeepSeek-R1 reasoning models.",
    status: "unconfigured",
    enabled: false,
    apiKey: "",
    baseUrl: "",
    defaultBaseUrl: "https://api.deepseek.com/v1",
    defaultModel: "deepseek-chat",
    models: [
      { id: "deepseek-chat", name: "DeepSeek Chat" },
      { id: "deepseek-reasoner", name: "DeepSeek Reasoner" },
    ],
    docsUrl: "https://api-docs.deepseek.com",
  },
  {
    id: "zai",
    name: "ZAI",
    short: "ZA",
    tint: "bg-[#22c55e]/15 text-[#22c55e]",
    description: "GLM-4 family models with tool-use and long context.",
    status: "unconfigured",
    enabled: false,
    apiKey: "",
    baseUrl: "",
    defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4",
    defaultModel: "glm-4.6",
    models: [
      { id: "glm-4.6", name: "GLM-4.6" },
      { id: "glm-4-plus", name: "GLM-4 Plus" },
    ],
    docsUrl: "https://open.bigmodel.cn/dev/api",
  },
];

// ---------------------------------------------------------------------------
// Derived selectors — one source of truth, many shapes.
// ---------------------------------------------------------------------------

/**
 * A trimmed catalog (id, name, models) for the agent configuration sheet and
 * anywhere else that only needs provider→models lookup.
 */
export const providerCatalog: ProviderCatalogEntry[] = providersData.map((p) => ({
  id: p.id,
  name: p.name,
  models: p.models,
}));

/**
 * Topbar `ProviderSelector` options — only the enabled/ready providers appear
 * so the global switcher doesn't offer unusable choices.
 */
export const topbarProviders: ProviderOption[] = providersData
  .filter((p) => p.enabled && p.status !== "unconfigured")
  .map((p) => ({
    id: p.id,
    name: p.name,
    status: p.status === "error" ? "error" : "ready",
  }));

/**
 * Topbar `ModelSelector` options — models from every enabled provider,
 * annotated with the provider name as the hint.
 */
export const topbarModels: ModelOption[] = providersData
  .filter((p) => p.enabled)
  .flatMap((p) =>
    p.models.map((m) => ({
      id: `${p.id}:${m.id}`,
      name: m.name,
      providerId: p.id,
      hint: p.name,
    })),
  );

/** Look up a provider by id, throwing during dev if missing. */
export function getProvider(id: string): Provider | undefined {
  return providersData.find((p) => p.id === id);
}
