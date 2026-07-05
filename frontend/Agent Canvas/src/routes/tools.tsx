import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { Settings as SettingsIcon, Plus } from "lucide-react";
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
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { tileToneClass } from "@/lib/status";

import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import {
  toolsService,
  TOOL_STATUS_META,
  type Tool,
  type ToolStatus,
} from "@/services";

const toolsData = toolsService.listSync();


export const Route = createFileRoute("/tools")({
  component: ToolsPage,
  head: () => ({
    meta: [
      { title: "Tools · Agent Reach Studio" },
      {
        name: "description",
        content:
          "Manage and configure the tools your agents can use — browsers, search, RSS, Telegram, HTTP and more.",
      },
      { property: "og:title", content: "Tools · Agent Reach Studio" },
      {
        property: "og:description",
        content: "Enable, disable and configure the tools available to your agents.",
      },
    ],
  }),
});

const FILTERS: { id: "all" | ToolStatus; label: string }[] = [
  { id: "all", label: "All" },
  { id: "ready", label: "Ready" },
  { id: "needs_config", label: "Needs config" },
  { id: "error", label: "Error" },
  { id: "disabled", label: "Disabled" },
];

function ToolsPage() {
  const onNavigate = useAppNavigation("tools");
  const topbar = useTopbar();
  const [tools, setTools] = React.useState<Tool[]>(toolsData);

  const [filter, setFilter] = React.useState<(typeof FILTERS)[number]["id"]>("all");
  const [configuring, setConfiguring] = React.useState<Tool | null>(null);

  const visible = React.useMemo(
    () => (filter === "all" ? tools : tools.filter((t) => t.status === filter)),
    [tools, filter],
  );

  const counts = React.useMemo(
    () => ({
      ready: tools.filter((t) => t.status === "ready").length,
      needs_config: tools.filter((t) => t.status === "needs_config").length,
      error: tools.filter((t) => t.status === "error").length,
    }),
    [tools],
  );

  const handleToggle = (tool: Tool, next: boolean) => {
    setTools((prev) =>
      prev.map((t) =>
        t.id === tool.id
          ? {
              ...t,
              enabled: next,
              status:
                t.status === "error" || t.status === "needs_config"
                  ? t.status
                  : next
                    ? "ready"
                    : "disabled",
            }
          : t,
      ),
    );
    toast(`${tool.name} ${next ? "enabled" : "disabled"}`);
  };

  const handleSaveConfig = (tool: Tool, values: Record<string, string>) => {
    const missing = tool.fields.filter((f) => f.required && !values[f.key]?.trim());
    if (missing.length > 0) {
      toast.error(`Missing required: ${missing.map((f) => f.label).join(", ")}`);
      return;
    }
    setTools((prev) =>
      prev.map((t) =>
        t.id === tool.id ? { ...t, status: t.enabled ? "ready" : "disabled" } : t,
      ),
    );
    setConfiguring(null);
    toast.success(`${tool.name} configured`);
  };

  return (
    <AppShell
      {...topbar}
      sidebarItems={defaultSidebarItems}
      activeSidebarId="tools"
      onNavigate={onNavigate}

    >
      <PageHeader
        eyebrow="Workspace"
        title="Tools"
        description="Extend your agents with browsers, search, feeds, messaging and more."
        actions={
          <>
            <div className="hidden sm:flex items-center gap-1.5">
              <Badge variant="success">{counts.ready} ready</Badge>
              {counts.needs_config > 0 && (
                <Badge variant="warning">{counts.needs_config} needs config</Badge>
              )}
              {counts.error > 0 && <Badge variant="destructive">{counts.error} error</Badge>}
            </div>
            <Button variant="accent" size="sm" onClick={() => toast("Custom tools coming soon")}>
              <Plus size={14} />
              Add tool
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
        {visible.map((tool) => (
          <ToolCard
            key={tool.id}
            tool={tool}
            onToggle={(v) => handleToggle(tool, v)}
            onConfigure={() => setConfiguring(tool)}
          />
        ))}
      </motion.div>

      {visible.length === 0 && (
        <EmptyState className="mt-8" title="No tools match this filter" />
      )}


      <ConfigureSheet
        tool={configuring}
        onOpenChange={(open) => !open && setConfiguring(null)}
        onSave={handleSaveConfig}
      />
    </AppShell>
  );
}

function ToolCard({
  tool,
  onToggle,
  onConfigure,
}: {
  tool: Tool;
  onToggle: (v: boolean) => void;
  onConfigure: () => void;
}) {
  const Icon = tool.icon;
  const meta = TOOL_STATUS_META[tool.status];
  const tileTone =
    tool.status === "error"
      ? "destructive"
      : tool.status === "needs_config"
        ? "warning"
        : tool.enabled
          ? "accent"
          : "muted";

  return (
    <Card className="flex flex-col transition-colors hover:border-border-strong">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-lg border border-border",
              tileToneClass(tileTone),
            )}
          >
            <Icon size={18} />
          </div>
          <div className="min-w-0">
            <CardTitle className="text-sm truncate">{tool.name}</CardTitle>
            <CardDescription className="mt-0.5 line-clamp-2">{tool.description}</CardDescription>
          </div>
        </div>
        <Switch
          checked={tool.enabled}
          onCheckedChange={onToggle}
          aria-label={`Toggle ${tool.name}`}
        />
      </CardHeader>
      <CardContent className="mt-auto flex items-center justify-between pt-2">
        <StatusIndicator tone={meta.tone} label={meta.label} pulse={tool.status === "ready"} />
        <Button variant="outline" size="sm" onClick={onConfigure}>
          <SettingsIcon size={13} />
          Configure
        </Button>
      </CardContent>
    </Card>
  );
}

function ConfigureSheet({
  tool,
  onOpenChange,
  onSave,
}: {
  tool: Tool | null;
  onOpenChange: (open: boolean) => void;
  onSave: (tool: Tool, values: Record<string, string>) => void;
}) {
  const [values, setValues] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (tool) setValues({});
  }, [tool?.id]);

  if (!tool) {
    return (
      <Sheet open={false} onOpenChange={onOpenChange}>
        <SheetContent />
      </Sheet>
    );
  }

  const Icon = tool.icon;
  const meta = TOOL_STATUS_META[tool.status];

  return (
    <Sheet open={!!tool} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md flex flex-col gap-0 p-0">
        <SheetHeader className="p-6 hairline-b">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-accent/15 text-accent border border-border">
              <Icon size={18} />
            </div>
            <div className="min-w-0">
              <SheetTitle className="truncate">{tool.name}</SheetTitle>
              <SheetDescription className="line-clamp-2">{tool.description}</SheetDescription>
            </div>
          </div>
          <div className="mt-4">
            <StatusIndicator tone={meta.tone} label={meta.label} />
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {tool.fields.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No configuration required for this tool.
            </p>
          )}
          {tool.fields.map((field) => (
            <div key={field.key} className="space-y-1.5">
              <Label htmlFor={`cfg-${field.key}`} className="flex items-center gap-1.5">
                {field.label}
                {field.required && <span className="text-destructive">*</span>}
              </Label>
              {field.type === "textarea" ? (
                <Textarea
                  id={`cfg-${field.key}`}
                  placeholder={field.placeholder}
                  value={values[field.key] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                  rows={4}
                  className="font-mono text-xs"
                />
              ) : (
                <Input
                  id={`cfg-${field.key}`}
                  type={field.type === "password" ? "password" : "text"}
                  inputMode={field.type === "url" ? "url" : undefined}
                  placeholder={field.placeholder}
                  value={values[field.key] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                />
              )}
              {field.description && (
                <p className="text-[11px] text-muted-foreground">{field.description}</p>
              )}
            </div>
          ))}
        </div>

        <SheetFooter className="p-6 hairline-t">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="accent" onClick={() => onSave(tool, values)}>
            Save configuration
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
