/**
 * Agent domain — the specialized workers the app exposes.
 *
 * A single source of truth for agent definitions. The Chat page's agent-mode
 * selector, the Agents page, and dashboard summaries all read from here.
 */

import { Search, Globe, Code2, Newspaper, PenLine, type LucideIcon } from "lucide-react";
import type { StatusTone } from "@/lib/status";

export type AgentStatus = "ready" | "disabled" | "needs_config" | "error";

export interface Agent {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
  /** Tile tint class pair — kept static so cards read consistently. */
  tint: string;
  status: AgentStatus;
  enabled: boolean;
  providerId: string;
  modelId: string;
  systemPrompt: string;
  temperature: number;
  maxTokens: number;
}

export const AGENT_STATUS_META: Record<AgentStatus, { label: string; tone: StatusTone }> = {
  ready: { label: "Ready", tone: "success" },
  disabled: { label: "Disabled", tone: "neutral" },
  needs_config: { label: "Needs config", tone: "warning" },
  error: { label: "Error", tone: "destructive" },
};

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

export const agentsData: Agent[] = [
  {
    id: "research",
    name: "Research Agent",
    description: "Deep web and document research with cited synthesis.",
    icon: Search,
    tint: "bg-accent/15 text-accent",
    status: "ready",
    enabled: true,
    providerId: "anthropic",
    modelId: "claude-sonnet-4",
    systemPrompt:
      "You are a rigorous research assistant. Gather sources, cite them, and synthesize concise findings.",
    temperature: 0.3,
    maxTokens: 4000,
  },
  {
    id: "browser",
    name: "Browser Agent",
    description: "Navigate websites and extract structured information.",
    icon: Globe,
    tint: "bg-info/15 text-info",
    status: "ready",
    enabled: true,
    providerId: "openai",
    modelId: "gpt-4o",
    systemPrompt:
      "You control a headless browser. Plan the shortest path to the goal and validate each step.",
    temperature: 0.2,
    maxTokens: 3000,
  },
  {
    id: "coding",
    name: "Coding Agent",
    description: "Read, write and refactor code across a repository.",
    icon: Code2,
    tint: "bg-success/15 text-success",
    status: "needs_config",
    enabled: false,
    providerId: "anthropic",
    modelId: "claude-opus-4",
    systemPrompt:
      "You are a senior engineer. Produce production-quality diffs with tests and clear commit messages.",
    temperature: 0.15,
    maxTokens: 6000,
  },
  {
    id: "news",
    name: "News Agent",
    description: "Track breaking headlines and produce daily summaries.",
    icon: Newspaper,
    tint: "bg-warning/15 text-warning",
    status: "disabled",
    enabled: false,
    providerId: "google",
    modelId: "gemini-2.5-flash",
    systemPrompt:
      "You summarize the day's most important news. Group by topic and cite sources.",
    temperature: 0.4,
    maxTokens: 2000,
  },
  {
    id: "content",
    name: "Content Agent",
    description: "Draft posts, emails and marketing copy in your voice.",
    icon: PenLine,
    tint: "bg-[#a855f7]/15 text-[#a855f7]",
    status: "error",
    enabled: true,
    providerId: "openai",
    modelId: "gpt-5",
    systemPrompt:
      "You are a versatile writer. Match the requested tone precisely and keep copy tight.",
    temperature: 0.7,
    maxTokens: 2500,
  },
];

// ---------------------------------------------------------------------------
// Derived views
// ---------------------------------------------------------------------------

/** Lightweight shape for the Chat page's agent-mode dropdown. */
export interface ChatAgentOption {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
}

export const chatAgents: ChatAgentOption[] = agentsData.map((a) => ({
  id: a.id,
  name: a.name,
  description: a.description,
  icon: a.icon,
}));
