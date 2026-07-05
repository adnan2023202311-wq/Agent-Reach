import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { Settings as SettingsIcon, Plus, Play } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";

import { StatusIndicator } from "@/components/common/status-indicator";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import {
  providersService,
  agentsService,
  AGENT_STATUS_META,
  type Agent,
  type AgentStatus,
} from "@/services";

const providerCatalog = providersService.catalogSync();
const agentsData = agentsService.listSync();


export const Route = createFileRoute("/agents")({
  component: AgentsPage,
  head: () => ({
    meta: [
      { title: "Agents · Agent Reach Studio" },
      {
        name: "description",
        content:
          "Manage your AI agents — assign providers, tune prompts and control how each agent responds.",
      },
      { property: "og:title", content: "Agents · Agent Reach Studio" },
      {
        property: "og:description",
        content: "Configure and run specialized AI agents from one place.",
      },
    ],
  }),
});

const FILTERS: { id: "all" | AgentStatus; label: string }[] = [
  { id: "all", label: "All" },
  { id: "ready", label: "Ready" },
  { id: "needs_config", label: "Needs config" },
  { id: "error", label: "Error" },
  { id: "disabled", label: "Disabled" },
];

const MAX_TOKENS_LIMIT = 16000;

function AgentsPage() {
  const onNavigate = useAppNavigation("agents");
  const topbar = useTopbar();
  const [agents, setAgents] = React.useState<Agent[]>(agentsData);

  const [filter, setFilter] = React.useState<(typeof FILTERS)[number]["id"]>("all");
  const [configuring, setConfiguring] = React.useState<Agent | null>(null);

  const visible = React.useMemo(
    () => (filter === "all" ? agents : agents.filter((a) => a.status === filter)),
    [agents, filter],
  );

  const counts = React.useMemo(
    () => ({
      ready: agents.filter((a) => a.status === "ready").length,
      needs_config: agents.filter((a) => a.status === "needs_config").length,
      error: agents.filter((a) => a.status === "error").length,
    }),
    [agents],
  );

  const patch = (id: string, next: Partial<Agent>) =>
    setAgents((prev) => prev.map((a) => (a.id === id ? { ...a, ...next } : a)));

  const handleToggle = (a: Agent, next: boolean) => {
    patch(a.id, {
      enabled: next,
      status:
        a.status === "error" || a.status === "needs_config"
          ? a.status
          : next
            ? "ready"
            : "disabled",
    });
    toast(`${a.name} ${next ? "enabled" : "disabled"}`);
  };

  const handleRun = (a: Agent) => {
    if (a.status !== "ready" || !a.enabled) {
      toast.error(`${a.name} isn't ready to run`);
      return;
    }
    toast.success(`Running ${a.name} (mocked)`);
  };

  const handleSave = (a: Agent, values: AgentConfigValues) => {
    patch(a.id, {
      providerId: values.providerId,
      modelId: values.modelId,
      systemPrompt: values.systemPrompt,
      temperature: values.temperature,
      maxTokens: values.maxTokens,
      status: a.enabled ? "ready" : "disabled",
    });
    setConfiguring(null);
    toast.success(`${a.name} updated`);
  };

  return (
    <AppShell
      {...topbar}
      sidebarItems={defaultSidebarItems}
      activeSidebarId="agents"
      onNavigate={onNavigate}

    >
      <PageHeader
        eyebrow="Workspace"
        title="Agents"
        description="Specialized workers that plan, use tools, and complete tasks on your behalf."
        actions={
          <>
            <div className="hidden sm:flex items-center gap-1.5">
              <Badge variant="success">{counts.ready} ready</Badge>
              {counts.needs_config > 0 && (
                <Badge variant="warning">{counts.needs_config} needs config</Badge>
              )}
              {counts.error > 0 && <Badge variant="destructive">{counts.error} error</Badge>}
            </div>
            <Button variant="accent" size="sm" onClick={() => toast("Custom agents coming soon")}>
              <Plus size={14} />
              New agent
            </Button>
          </>
        }
      />

      <Tabs value={filter} onValueChange={(v) => setFilter(v as typeof filter)} className="mb-5">
        <TabsList>
          {FILTERS.map((f) => (
            <TabsTrigger key={f.id} value={f.id}>
              {f.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {visible.map((a) => (
          <AgentCard
            key={a.id}
            agent={a}
            onToggle={(v) => handleToggle(a, v)}
            onRun={() => handleRun(a)}
            onConfigure={() => setConfiguring(a)}
          />
        ))}
      </motion.div>

      {visible.length === 0 && (
        <EmptyState className="mt-8" title="No agents match this filter" />
      )}


      <ConfigureSheet
        agent={configuring}
        onOpenChange={(open) => !open && setConfiguring(null)}
        onSave={handleSave}
      />
    </AppShell>
  );
}

// ---------- Card ----------
function AgentCard({
  agent,
  onToggle,
  onRun,
  onConfigure,
}: {
  agent: Agent;
  onToggle: (v: boolean) => void;
  onRun: () => void;
  onConfigure: () => void;
}) {
  const Icon = agent.icon;
  const meta = AGENT_STATUS_META[agent.status];
  const provider = providerCatalog.find((p) => p.id === agent.providerId);
  const modelName =
    provider?.models.find((m) => m.id === agent.modelId)?.name ?? agent.modelId;
  const canRun = agent.enabled && agent.status === "ready";

  return (
    <Card className="flex flex-col transition-colors hover:border-border-strong">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-lg border border-border",
              agent.tint,
            )}
          >
            <Icon size={18} />
          </div>
          <div className="min-w-0">
            <CardTitle className="text-sm truncate">{agent.name}</CardTitle>
            <CardDescription className="mt-0.5 line-clamp-2">
              {agent.description}
            </CardDescription>
          </div>
        </div>
        <Switch
          checked={agent.enabled}
          onCheckedChange={onToggle}
          aria-label={`Toggle ${agent.name}`}
        />
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-3">
        <dl className="grid gap-2 text-xs">
          <MetaRow label="Provider" value={provider?.name ?? agent.providerId} />
          <MetaRow label="Default model" value={modelName} mono truncate />
        </dl>

        <div className="mt-auto flex items-center justify-between pt-1">
          <StatusIndicator
            tone={meta.tone}
            label={meta.label}
            pulse={agent.status === "ready" && agent.enabled}
          />
          <div className="flex items-center gap-1.5">
            <Button variant="outline" size="sm" onClick={onConfigure}>
              <SettingsIcon size={13} />
              Configure
            </Button>
            <Button variant="accent" size="sm" onClick={onRun} disabled={!canRun}>
              <Play size={13} />
              Run
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function MetaRow({
  label,
  value,
  mono,
  truncate,
}: {
  label: string;
  value: string;
  mono?: boolean;
  truncate?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd
        className={cn(
          "min-w-0 text-right text-foreground",
          mono && "font-mono text-[11px]",
          truncate && "truncate",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

// ---------- Configure Sheet ----------
interface AgentConfigValues {
  providerId: string;
  modelId: string;
  systemPrompt: string;
  temperature: number;
  maxTokens: number;
}

function ConfigureSheet({
  agent,
  onOpenChange,
  onSave,
}: {
  agent: Agent | null;
  onOpenChange: (open: boolean) => void;
  onSave: (agent: Agent, values: AgentConfigValues) => void;
}) {
  const [values, setValues] = React.useState<AgentConfigValues>({
    providerId: "",
    modelId: "",
    systemPrompt: "",
    temperature: 0.5,
    maxTokens: 2000,
  });

  React.useEffect(() => {
    if (!agent) return;
    setValues({
      providerId: agent.providerId,
      modelId: agent.modelId,
      systemPrompt: agent.systemPrompt,
      temperature: agent.temperature,
      maxTokens: agent.maxTokens,
    });
  }, [agent?.id]);

  if (!agent) {
    return (
      <Sheet open={false} onOpenChange={onOpenChange}>
        <SheetContent />
      </Sheet>
    );
  }

  const Icon = agent.icon;
  const meta = AGENT_STATUS_META[agent.status];
  const provider = providerCatalog.find((p) => p.id === values.providerId);
  const availableModels = provider?.models ?? [];

  const handleProviderChange = (providerId: string) => {
    const next = providerCatalog.find((p) => p.id === providerId);
    setValues((v) => ({ ...v, providerId, modelId: next?.models[0]?.id ?? "" }));
  };

  const handleMaxTokensChange = (raw: string) => {
    const parsed = Number.parseInt(raw, 10);
    if (Number.isNaN(parsed)) {
      setValues((v) => ({ ...v, maxTokens: 0 }));
      return;
    }
    setValues((v) => ({
      ...v,
      maxTokens: Math.min(Math.max(parsed, 1), MAX_TOKENS_LIMIT),
    }));
  };

  return (
    <Sheet open={!!agent} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md flex flex-col gap-0 p-0">
        <SheetHeader className="p-6 hairline-b">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex size-10 items-center justify-center rounded-lg border border-border",
                agent.tint,
              )}
            >
              <Icon size={18} />
            </div>
            <div className="min-w-0">
              <SheetTitle className="truncate">{agent.name}</SheetTitle>
              <SheetDescription className="line-clamp-2">
                {agent.description}
              </SheetDescription>
            </div>
          </div>
          <div className="mt-4">
            <StatusIndicator tone={meta.tone} label={meta.label} />
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="cfg-provider">Default provider</Label>
              <Select value={values.providerId} onValueChange={handleProviderChange}>
                <SelectTrigger id="cfg-provider">
                  <SelectValue placeholder="Choose provider" />
                </SelectTrigger>
                <SelectContent>
                  {providerCatalog.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cfg-model">Default model</Label>
              <Select
                value={values.modelId}
                onValueChange={(modelId) => setValues((v) => ({ ...v, modelId }))}
                disabled={availableModels.length === 0}
              >
                <SelectTrigger id="cfg-model">
                  <SelectValue placeholder="Choose model" />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cfg-prompt">System prompt</Label>
            <Textarea
              id="cfg-prompt"
              rows={6}
              value={values.systemPrompt}
              onChange={(e) => setValues((v) => ({ ...v, systemPrompt: e.target.value }))}
              placeholder="Describe the agent's role, style and constraints…"
              className="text-xs leading-relaxed"
            />
            <p className="text-[11px] text-muted-foreground">
              Prepended to every conversation this agent handles.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="cfg-temp">Temperature</Label>
              <span className="font-mono text-xs text-muted-foreground">
                {values.temperature.toFixed(2)}
              </span>
            </div>
            <Slider
              id="cfg-temp"
              min={0}
              max={2}
              step={0.05}
              value={[values.temperature]}
              onValueChange={([t]) => setValues((v) => ({ ...v, temperature: t }))}
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>Focused</span>
              <span>Balanced</span>
              <span>Creative</span>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="cfg-max-tokens">Max tokens</Label>
              <span className="font-mono text-[11px] text-muted-foreground">
                up to {MAX_TOKENS_LIMIT.toLocaleString()}
              </span>
            </div>
            <Input
              id="cfg-max-tokens"
              type="number"
              min={1}
              max={MAX_TOKENS_LIMIT}
              value={values.maxTokens}
              onChange={(e) => handleMaxTokensChange(e.target.value)}
              className="font-mono text-xs"
            />
            <p className="text-[11px] text-muted-foreground">
              Upper bound on the agent's response length.
            </p>
          </div>
        </div>

        <SheetFooter className="p-6 hairline-t">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="accent" onClick={() => onSave(agent, values)}>
            Save changes
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
