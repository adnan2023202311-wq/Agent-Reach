/**
 * Chat domain — types shared by the composer, message list, and empty state,
 * plus the starter prompts we show before the first message.
 */

import { Lightbulb, BookOpen, Code2, Rocket, Search, Globe, Wand2, type LucideIcon } from "lucide-react";

export type ChatMode = "chat" | "agent";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  mode?: ChatMode;
  agentId?: string;
}

export interface Suggestion {
  icon: LucideIcon;
  title: string;
  prompt: string;
}

export const chatSuggestions: Suggestion[] = [
  {
    icon: Lightbulb,
    title: "Brainstorm ideas",
    prompt: "Give me 10 unconventional ideas for a weekend side project.",
  },
  {
    icon: BookOpen,
    title: "Explain a concept",
    prompt: "Explain how vector databases work, with a simple example.",
  },
  {
    icon: Code2,
    title: "Write code",
    prompt: "Write a TypeScript function that debounces an async function.",
  },
  {
    icon: Rocket,
    title: "Improve my writing",
    prompt: "Rewrite this paragraph to be clearer and more concise: …",
  },
];

export const agentSuggestions: Suggestion[] = [
  {
    icon: Search,
    title: "Research a topic",
    prompt: "Research the current state of on-device LLMs and summarize findings.",
  },
  {
    icon: Globe,
    title: "Browse the web",
    prompt: "Find the top 5 pricing pages for AI coding assistants.",
  },
  {
    icon: Code2,
    title: "Ship a feature",
    prompt: "Add dark-mode support to a React app and open a PR.",
  },
  {
    icon: Wand2,
    title: "Automate a task",
    prompt: "Draft a weekly digest email from my starred articles.",
  },
];

/** Composer limits — surfaced to the character counter and validator. */
export const CHAT_MAX_CHARS = 4000;

// ---------------------------------------------------------------------------
// Recent chats — shared history snapshot consumed by the Dashboard and any
// future "resume chat" surfaces. Kept here so the chat domain owns its data.
// ---------------------------------------------------------------------------

export interface RecentChat {
  id: string;
  title: string;
  snippet: string;
  provider: string;
  model: string;
  updatedAt: string;
}

export const recentChats: RecentChat[] = [
  {
    id: "c1",
    title: "Refactor auth middleware",
    snippet: "Extract the token verification into a shared helper and cover…",
    provider: "Anthropic",
    model: "Claude Sonnet 4",
    updatedAt: "2m ago",
  },
  {
    id: "c2",
    title: "Weekly product digest",
    snippet: "Summarize the top 5 releases from this week's changelog…",
    provider: "OpenRouter",
    model: "openai/gpt-5",
    updatedAt: "38m ago",
  },
  {
    id: "c3",
    title: "Explain vector databases",
    snippet: "A short primer for the onboarding docs, with a code example…",
    provider: "Google",
    model: "Gemini 2.5 Pro",
    updatedAt: "2h ago",
  },
  {
    id: "c4",
    title: "SQL query for retention",
    snippet: "Write a Postgres query for 4-week rolling retention grouped by…",
    provider: "Anthropic",
    model: "Claude Opus 4",
    updatedAt: "yesterday",
  },
];
