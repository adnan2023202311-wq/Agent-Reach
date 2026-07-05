/**
 * Tool domain — external capabilities agents can call.
 *
 * Field definitions live on the tool itself so the Configure sheet can render
 * the correct inputs generically.
 */

import { Globe, Search, Rss, Send, Network, FolderTree, type LucideIcon } from "lucide-react";
import type { StatusTone } from "@/lib/status";

export type ToolStatus = "ready" | "disabled" | "needs_config" | "error";

export interface ConfigField {
  key: string;
  label: string;
  type: "text" | "password" | "url" | "textarea";
  placeholder?: string;
  description?: string;
  required?: boolean;
}

export interface Tool {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
  status: ToolStatus;
  enabled: boolean;
  fields: ConfigField[];
}

export const TOOL_STATUS_META: Record<ToolStatus, { label: string; tone: StatusTone }> = {
  ready: { label: "Ready", tone: "success" },
  disabled: { label: "Disabled", tone: "neutral" },
  needs_config: { label: "Needs config", tone: "warning" },
  error: { label: "Error", tone: "destructive" },
};

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

export const toolsData: Tool[] = [
  {
    id: "browser",
    name: "Browser",
    description: "Headless web browsing, navigation and scraping.",
    icon: Globe,
    status: "ready",
    enabled: true,
    fields: [
      { key: "userAgent", label: "User Agent", type: "text", placeholder: "Mozilla/5.0 …" },
      { key: "timeoutMs", label: "Timeout (ms)", type: "text", placeholder: "30000" },
    ],
  },
  {
    id: "search",
    name: "Search",
    description: "Query the web across multiple search providers.",
    icon: Search,
    status: "ready",
    enabled: true,
    fields: [
      { key: "apiKey", label: "API Key", type: "password", placeholder: "sk-…", required: true },
      { key: "engine", label: "Engine", type: "text", placeholder: "tavily / brave / serpapi" },
    ],
  },
  {
    id: "rss",
    name: "RSS",
    description: "Subscribe to feeds and pull latest items.",
    icon: Rss,
    status: "disabled",
    enabled: false,
    fields: [
      {
        key: "feeds",
        label: "Feed URLs",
        type: "textarea",
        placeholder: "https://example.com/feed.xml\nhttps://news.site/rss",
        description: "One URL per line.",
      },
    ],
  },
  {
    id: "telegram",
    name: "Telegram",
    description: "Send and receive messages via a Telegram bot.",
    icon: Send,
    status: "needs_config",
    enabled: false,
    fields: [
      {
        key: "botToken",
        label: "Bot Token",
        type: "password",
        placeholder: "123456:ABC-DEF…",
        required: true,
      },
      { key: "chatId", label: "Default Chat ID", type: "text", placeholder: "-1001234567890" },
    ],
  },
  {
    id: "http",
    name: "HTTP Requests",
    description: "Make authenticated calls to any REST endpoint.",
    icon: Network,
    status: "ready",
    enabled: true,
    fields: [
      { key: "baseUrl", label: "Base URL", type: "url", placeholder: "https://api.example.com" },
      {
        key: "headers",
        label: "Default Headers",
        type: "textarea",
        placeholder: `{\n  "Authorization": "Bearer …"\n}`,
        description: "JSON object, merged into every request.",
      },
    ],
  },
  {
    id: "filesystem",
    name: "File System",
    description: "Read and write files inside the workspace sandbox.",
    icon: FolderTree,
    status: "error",
    enabled: true,
    fields: [
      {
        key: "rootPath",
        label: "Root Path",
        type: "text",
        placeholder: "/workspace",
        required: true,
      },
      {
        key: "allowWrites",
        label: "Allowed Extensions",
        type: "text",
        placeholder: ".md,.txt,.json",
      },
    ],
  },
];
