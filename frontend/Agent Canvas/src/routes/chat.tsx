import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessagesSquare,
  Paperclip,
  ArrowUp,
  Bot,
  User,
  Sparkles,
  Plus,
  Copy,
  Check,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import {
  agentsService,
  chatService,
  CHAT_MAX_CHARS,
  type ChatAgentOption,
  type ChatMode,
  type Message,
  type Suggestion,
  type ProviderOption,
  type ModelOption,
} from "@/services";

const chatAgents = agentsService.chatOptions();
const chatSuggestions = chatService.suggestions("chat");
const agentSuggestions = chatService.suggestions("agent");


export const Route = createFileRoute("/chat")({
  component: ChatPage,
  head: () => ({
    meta: [
      { title: "Chat · Agent Reach Studio" },
      {
        name: "description",
        content:
          "Chat with any model or delegate to a specialized agent inside Agent Reach Studio.",
      },
      { property: "og:title", content: "Chat · Agent Reach Studio" },
      {
        property: "og:description",
        content: "Chat with any model or delegate to a specialized agent.",
      },
    ],
  }),
});

function ChatPage() {
  const onNavigate = useAppNavigation("chat");
  const topbar = useTopbar();
  const { activeProvider: provider, activeModel: model } = topbar;

  const [mode, setMode] = React.useState<ChatMode>("chat");
  const [agent, setAgent] = React.useState(chatAgents[0]);
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [draft, setDraft] = React.useState("");
  const [files, setFiles] = React.useState<File[]>([]);

  const scrollerRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    scrollerRef.current?.scrollTo({
      top: scrollerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length]);

  React.useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [draft]);

  const suggestions = mode === "agent" ? agentSuggestions : chatSuggestions;
  const trimmed = draft.trim();
  const canSend = trimmed.length > 0 && trimmed.length <= CHAT_MAX_CHARS;

  const [sending, setSending] = React.useState(false);

  const sendMessage = async (text: string) => {
    const value = text.trim();
    if (!value || sending) return;
    const now = Date.now();
    const user: Message = { id: `u_${now}`, role: "user", content: value, createdAt: now, mode, agentId: mode === "agent" ? agent.id : undefined };
    setMessages((m) => [...m, user]);
    setDraft("");
    setFiles([]);
    setSending(true);
    try {
      // Milestone 8 — Production API integration
      // Uses chatService.sendMessage which calls /api/v1/conversations/... → IntelligentPipeline
      const reply = await chatService.sendMessage({
        content: value,
        mode,
        providerId: provider.id,
        modelId: model.id.replace(`${provider.id}:`, ""),
        agentId: mode === "agent" ? agent.id : undefined,
      });
      // Normalize reply shape to Message
      const assistant: Message = {
        id: reply.id || `a_${Date.now()}`,
        role: "assistant",
        content: reply.content,
        createdAt: typeof reply.createdAt === "string" ? new Date(reply.createdAt).getTime() : (reply.createdAt || Date.now()),
        mode: reply.mode || mode,
        agentId: reply.agentId || (mode === "agent" ? agent.id : undefined),
      };
      setMessages((m) => [...m, assistant]);
    } catch (err: any) {
      toast.error(err?.message || "Failed to send message");
      // Fallback to mock reply to keep UI responsive in dev
      const fallback: Message = {
        id: `a_${Date.now()}`,
        role: "assistant",
        content: buildMockReply(value, mode, mode === "agent" ? agent : null),
        createdAt: Date.now(),
        mode,
        agentId: mode === "agent" ? agent.id : undefined,
      };
      setMessages((m) => [...m, fallback]);
    } finally {
      setSending(false);
    }
  };

  const handleSend = () => {
    if (!canSend || sending) return;
    void sendMessage(draft);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const next = Array.from(list);
    setFiles((f) => [...f, ...next]);
    toast(`${next.length} file${next.length > 1 ? "s" : ""} attached (UI only)`);
  };

  const handleNewChat = () => {
    setMessages([]);
    setDraft("");
    setFiles([]);
    textareaRef.current?.focus();
  };

  const handleRegenerate = (id: string) => {
    const idx = messages.findIndex((m) => m.id === id);
    if (idx <= 0) return;
    const prevUser = [...messages.slice(0, idx)].reverse().find((m) => m.role === "user");
    if (!prevUser) return;
    const now = Date.now();
    const regenerated: Message = {
      id: `a_${now}`,
      role: "assistant",
      content: buildMockReply(prevUser.content, mode, mode === "agent" ? agent : null, true),
      createdAt: now,
    };
    setMessages((m) => m.map((msg, i) => (i === idx ? regenerated : msg)));
  };

  const charCount = draft.length;
  const overLimit = charCount > CHAT_MAX_CHARS;

  return (
    <TooltipProvider delayDuration={200}>
      <AppShell
        {...topbar}
        sidebarItems={defaultSidebarItems}
        activeSidebarId="chat"
        onNavigate={onNavigate}
      >

        <PageHeader
          eyebrow="Workspace"
          title="Chat"
          description="Talk to a model directly, or hand the conversation to an agent."
          actions={
            <>
              <ModeToggle value={mode} onChange={setMode} />
              {mode === "agent" && <AgentSelector value={agent} onChange={setAgent} />}
              <Button variant="outline" size="sm" onClick={handleNewChat}>
                <Plus size={14} />
                New chat
              </Button>
            </>
          }
        />

        <div className="flex flex-col h-[calc(100dvh-14rem)] min-h-[560px] rounded-xl border border-border bg-surface/40 overflow-hidden">
          <div ref={scrollerRef} className="flex-1 overflow-y-auto scroll-smooth">
            {messages.length === 0 ? (
              <EmptyChat
                mode={mode}
                agent={mode === "agent" ? agent : null}
                model={model}
                provider={provider}
                suggestions={suggestions}
                onPick={(p) => sendMessage(p)}
              />
            ) : (
              <div className="mx-auto w-full max-w-3xl px-4 sm:px-6 py-6 space-y-6">
                <AnimatePresence initial={false}>
                  {messages.map((m) => (
                    <MessageRow
                      key={m.id}
                      message={m}
                      onRegenerate={() => handleRegenerate(m.id)}
                    />
                  ))}
                </AnimatePresence>
              </div>
            )}
          </div>

          <div className="sticky bottom-0 border-t border-border bg-background/80 backdrop-blur-xl">
            <div className="mx-auto w-full max-w-3xl px-4 sm:px-6 py-4">
              {files.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {files.map((f, i) => (
                    <Badge key={i} variant="subtle" className="gap-1.5">
                      <Paperclip size={11} />
                      <span className="max-w-[160px] truncate">{f.name}</span>
                      <button
                        type="button"
                        onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                        className="ml-1 text-muted-foreground hover:text-foreground"
                        aria-label={`Remove ${f.name}`}
                      >
                        ×
                      </button>
                    </Badge>
                  ))}
                </div>
              )}

              <div
                className={cn(
                  "group relative flex items-end gap-2 rounded-xl border bg-surface p-2 transition-colors",
                  overLimit
                    ? "border-destructive/60"
                    : "border-border focus-within:border-border-strong focus-within:ring-2 focus-within:ring-ring/40",
                )}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => handleFiles(e.target.files)}
                />
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => fileInputRef.current?.click()}
                      aria-label="Attach file"
                    >
                      <Paperclip size={16} />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Attach files (UI only)</TooltipContent>
                </Tooltip>

                <Textarea
                  ref={textareaRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                  placeholder={
                    mode === "agent"
                      ? `Describe a task for ${agent.name}…`
                      : `Message ${model.name}…`
                  }
                  className="min-h-[36px] max-h-52 resize-none border-0 bg-transparent px-1 py-1.5 shadow-none focus-visible:ring-0"
                />

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="accent"
                      size="icon-sm"
                      onClick={handleSend}
                      disabled={!canSend}
                      aria-label="Send message"
                    >
                      <ArrowUp size={16} />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Send · Enter</TooltipContent>
                </Tooltip>
              </div>

              <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                <span className="hidden sm:inline">
                  <kbd className="rounded border border-border bg-surface px-1 py-0.5 font-mono text-[10px]">
                    Enter
                  </kbd>{" "}
                  to send ·{" "}
                  <kbd className="rounded border border-border bg-surface px-1 py-0.5 font-mono text-[10px]">
                    Shift + Enter
                  </kbd>{" "}
                  for newline
                </span>
                <span
                  className={cn(
                    "ml-auto font-mono",
                    overLimit ? "text-destructive" : "text-muted-foreground/70",
                  )}
                  aria-live="polite"
                >
                  {charCount.toLocaleString()} / {CHAT_MAX_CHARS.toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      </AppShell>
    </TooltipProvider>
  );
}

// ---------- Mode toggle ----------
function ModeToggle({ value, onChange }: { value: ChatMode; onChange: (v: ChatMode) => void }) {
  const options: { id: ChatMode; label: string; icon: React.ComponentType<{ size?: number }> }[] = [
    { id: "chat", label: "Chat", icon: MessagesSquare },
    { id: "agent", label: "Agent", icon: Sparkles },
  ];
  return (
    <div
      role="tablist"
      aria-label="Chat mode"
      className="inline-flex items-center rounded-lg border border-border bg-surface p-0.5"
    >
      {options.map((o) => {
        const Icon = o.icon;
        const active = value === o.id;
        return (
          <button
            key={o.id}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(o.id)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              active
                ? "bg-surface-hover text-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon size={13} />
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ---------- Agent selector ----------
function AgentSelector({
  value,
  onChange,
}: {
  value: ChatAgentOption;
  onChange: (a: ChatAgentOption) => void;
}) {
  const Icon = value.icon;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Icon size={14} className="text-accent" />
          <span className="max-w-[140px] truncate">{value.name}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
          Agents
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {chatAgents.map((a) => {
          const AIcon = a.icon;
          const active = a.id === value.id;
          return (
            <DropdownMenuItem
              key={a.id}
              onSelect={() => onChange(a)}
              className="flex items-start gap-2.5 py-2"
            >
              <div className="mt-0.5 flex size-6 items-center justify-center rounded-md bg-accent/15 text-accent">
                <AIcon size={13} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium">{a.name}</div>
                <div className="text-[11px] text-muted-foreground truncate">{a.description}</div>
              </div>
              {active && <Check size={13} className="mt-1.5 text-accent" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------- Empty state ----------
function EmptyChat({
  mode,
  agent,
  model,
  provider,
  suggestions,
  onPick,
}: {
  mode: ChatMode;
  agent: ChatAgentOption | null;
  model: ModelOption;
  provider: ProviderOption;
  suggestions: Suggestion[];
  onPick: (prompt: string) => void;
}) {
  const title = mode === "agent" ? `Delegate to ${agent?.name}` : "How can I help you today?";
  const description =
    mode === "agent"
      ? "Describe an outcome — the agent will plan and execute the steps."
      : `Chatting with ${model.name} via ${provider.name}. Pick a starter or type your own message below.`;

  return (
    <div className="h-full flex items-center justify-center px-4 sm:px-6 py-10">
      <div className="w-full max-w-2xl text-center">
        <div className="mx-auto mb-5 flex size-12 items-center justify-center rounded-xl bg-accent/15 text-accent">
          {mode === "agent" ? <Bot size={22} /> : <Sparkles size={22} />}
        </div>
        <h2 className="text-xl font-semibold tracking-tight text-foreground text-balance">
          {title}
        </h2>
        <p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">{description}</p>

        <div className="mt-8 grid gap-2.5 sm:grid-cols-2">
          {suggestions.map((s, i) => {
            const Icon = s.icon;
            return (
              <button
                key={i}
                type="button"
                onClick={() => onPick(s.prompt)}
                className="group flex items-start gap-3 rounded-xl border border-border bg-surface p-3.5 text-left transition-colors hover:bg-surface-hover hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-surface-hover text-muted-foreground group-hover:text-accent transition-colors">
                  <Icon size={14} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-foreground">{s.title}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
                    {s.prompt}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------- Message row ----------
function MessageRow({
  message,
  onRegenerate,
}: {
  message: Message;
  onRegenerate: () => void;
}) {
  const isUser = message.role === "user";
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className={cn("group flex gap-3", isUser ? "justify-end" : "justify-start")}
    >
      {!isUser && (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
          <Bot size={15} />
        </div>
      )}

      <div
        className={cn(
          "flex flex-col min-w-0",
          isUser ? "items-end" : "items-start",
          "max-w-[85%]",
        )}
      >
        <div
          className={cn(
            "rounded-xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-primary text-primary-foreground rounded-br-sm whitespace-pre-wrap"
              : "bg-surface border border-border text-foreground rounded-bl-sm",
          )}
        >
          {isUser ? message.content : <MarkdownContent content={message.content} />}
        </div>

        <div
          className={cn(
            "mt-1.5 flex items-center gap-1 text-[11px] text-muted-foreground/80",
            isUser ? "flex-row-reverse" : "flex-row",
          )}
        >
          <span className="font-mono px-1">{formatTime(message.createdAt)}</span>
          {!isUser && (
            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="h-6 w-6"
                    onClick={handleCopy}
                    aria-label="Copy response"
                  >
                    {copied ? <Check size={12} /> : <Copy size={12} />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{copied ? "Copied" : "Copy"}</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="h-6 w-6"
                    onClick={onRegenerate}
                    aria-label="Regenerate response"
                  >
                    <RefreshCw size={12} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Regenerate</TooltipContent>
              </Tooltip>
            </div>
          )}
        </div>
      </div>

      {isUser && (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface border border-border text-muted-foreground">
          <User size={15} />
        </div>
      )}
    </motion.div>
  );
}

// ---------- Markdown ----------
function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
          h1: ({ children }) => <h1 className="text-lg font-semibold mt-3 mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-base font-semibold mt-3 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1.5">{children}</h3>,
          ul: ({ children }) => (
            <ul className="mb-2 last:mb-0 list-disc pl-5 space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-2 last:mb-0 list-decimal pl-5 space-y-1">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-accent underline underline-offset-2 hover:opacity-80"
            >
              {children}
            </a>
          ),
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-border pl-3 italic text-muted-foreground my-2">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-3 border-border" />,
          code: ({ className, children, ...props }) => {
            const isInline =
              !(
                props as {
                  node?: { position?: { start: { line: number }; end: { line: number } } };
                }
              ).node?.position || !String(children).includes("\n");
            if (isInline) {
              return (
                <code className="rounded bg-surface-hover border border-border px-1 py-0.5 font-mono text-[12px]">
                  {children}
                </code>
              );
            }
            const lang = /language-(\w+)/.exec(className || "")?.[1];
            return <CodeBlock language={lang}>{String(children).replace(/\n$/, "")}</CodeBlock>;
          },
          pre: ({ children }) => <>{children}</>,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto rounded-md border border-border">
              <table className="w-full text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-border bg-surface-hover px-2.5 py-1.5 text-left font-medium">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border/60 px-2.5 py-1.5">{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function CodeBlock({ language, children }: { language?: string; children: string }) {
  const [copied, setCopied] = React.useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <div className="group/code my-2 overflow-hidden rounded-lg border border-border bg-background">
      <div className="flex items-center justify-between border-b border-border bg-surface px-3 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-surface-hover transition-colors"
          aria-label="Copy code"
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-[12.5px] leading-relaxed">
        <code className="font-mono text-foreground">{children}</code>
      </pre>
    </div>
  );
}

// ---------- helpers ----------
function formatTime(ts: number) {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function buildMockReply(
  input: string,
  mode: ChatMode,
  agent: ChatAgentOption | null,
  regenerated = false,
): string {
  const preface = regenerated ? "_Regenerated response._\n\n" : "";
  if (mode === "agent" && agent) {
    return `${preface}**${agent.name}** received your task:

> ${input}

Here's a mock plan:

1. Parse the request and clarify unknowns
2. Gather context via connected tools
3. Draft the response and validate results

\`\`\`ts
// Example step the agent would run
async function run(input: string) {
  const ctx = await tools.search(input);
  return await model.generate({ input, ctx });
}
\`\`\`

Backend execution is not yet connected.`;
  }

  return `${preface}Here's a mock response to:

> ${input}

- Markdown is rendered inline
- Lists, links and \`inline code\` all work
- Code blocks include a copy button

\`\`\`ts
export function greet(name: string) {
  return \`Hello, \${name}!\`;
}
\`\`\`

Connect a provider to see real model output.`;
}
