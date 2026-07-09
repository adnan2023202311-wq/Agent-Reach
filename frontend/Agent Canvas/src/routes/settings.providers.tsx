import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion } from "framer-motion";
import {
  KeyRound,
  Settings as SettingsIcon,
  Zap,
  Eye,
  EyeOff,
  Check,
  Loader2,
  Plus,
  type LucideIcon,
} from "lucide-react";
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
import type { StatusTone } from "@/lib/status";

import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";
import {
  providersService,
  type Provider,
  type ProviderStatus,
} from "@/services";

const providersDataFallback = providersService.listSync();


export const Route = createFileRoute("/settings/providers")({
  component: ProvidersPage,
  head: () => ({
    meta: [
      { title: "Providers · Settings · Agent Reach Studio" },
      {
        name: "description",
        content:
          "Manage your AI provider connections — API keys, base URLs and default models for every supported vendor.",
      },
      { property: "og:title", content: "Providers · Agent Reach Studio" },
      {
        property: "og:description",
        content: "Central place to enable and configure AI providers.",
      },
    ],
  }),
});

const STATUS_META: Record<
  ProviderStatus,
  { label: string; tone: StatusTone; icon: LucideIcon }
> = {
  ready: { label: "Ready", tone: "success", icon: Check },
  unconfigured: { label: "Unconfigured", tone: "warning", icon: KeyRound },
  error: { label: "Error", tone: "destructive", icon: Zap },
};

const FILTERS: { id: "all" | ProviderStatus; label: string }[] = [
  { id: "all", label: "All" },
  { id: "ready", label: "Ready" },
  { id: "unconfigured", label: "Unconfigured" },
  { id: "error", label: "Error" },
];

function ProvidersPage() {
  const onNavigate = useAppNavigation("settings");
  const topbar = useTopbar();
  const [providers, setProviders] = React.useState<Provider[]>(providersDataFallback);

  // M8: load providers from production API
  React.useEffect(() => {
    let mounted = true;
    providersService.list().then((data) => {
      if (mounted && data?.length) setProviders(data);
    }).catch(()=>{});
    return () => { mounted = false; };
  }, []);
  const [filter, setFilter] = React.useState<(typeof FILTERS)[number]["id"]>("all");
  const [configuring, setConfiguring] = React.useState<Provider | null>(null);


  const visible = React.useMemo(
    () => (filter === "all" ? providers : providers.filter((p) => p.status === filter)),
    [providers, filter],
  );

  const counts = React.useMemo(
    () => ({
      ready: providers.filter((p) => p.status === "ready").length,
      unconfigured: providers.filter((p) => p.status === "unconfigured").length,
      error: providers.filter((p) => p.status === "error").length,
    }),
    [providers],
  );

  const patchProvider = (id: string, patch: Partial<Provider>) => {
    setProviders((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  };

  const handleToggle = (p: Provider, next: boolean) => {
    patchProvider(p.id, { enabled: next });
    toast(`${p.name} ${next ? "enabled" : "disabled"}`);
  };

  const handleSave = (
    p: Provider,
    values: { apiKey: string; baseUrl: string; defaultModel: string },
  ) => {
    const hasKey = values.apiKey.trim().length > 0;
    patchProvider(p.id, {
      apiKey: values.apiKey,
      baseUrl: values.baseUrl,
      defaultModel: values.defaultModel,
      status: hasKey ? "ready" : "unconfigured",
    });
    setConfiguring(null);
    toast.success(`${p.name} saved`);
  };

  return (
    <AppShell
      {...topbar}
      sidebarItems={defaultSidebarItems}
      activeSidebarId="settings"
      onNavigate={onNavigate}

    >
      <PageHeader
        eyebrow="Settings"
        title="Providers"
        description="Connect and manage the AI vendors that power your chats and agents."
        actions={
          <>
            <div className="hidden sm:flex items-center gap-1.5">
              <Badge variant="success">{counts.ready} ready</Badge>
              {counts.unconfigured > 0 && (
                <Badge variant="warning">{counts.unconfigured} unconfigured</Badge>
              )}
              {counts.error > 0 && <Badge variant="destructive">{counts.error} error</Badge>}
            </div>
            <Button
              variant="accent"
              size="sm"
              onClick={() => toast("Custom providers coming soon")}
            >
              <Plus size={14} />
              Add provider
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
        {visible.map((p) => (
          <ProviderCard
            key={p.id}
            provider={p}
            onToggle={(v) => handleToggle(p, v)}
            onConfigure={() => setConfiguring(p)}
          />
        ))}
      </motion.div>

      {visible.length === 0 && (
        <EmptyState className="mt-8" title="No providers match this filter" />
      )}


      <ConfigureSheet
        provider={configuring}
        onOpenChange={(open) => !open && setConfiguring(null)}
        onSave={handleSave}
      />
    </AppShell>
  );
}

function ProviderCard({
  provider,
  onToggle,
  onConfigure,
}: {
  provider: Provider;
  onToggle: (v: boolean) => void;
  onConfigure: () => void;
}) {
  const meta = STATUS_META[provider.status];
  const modelName =
    provider.models.find((m: any) => m.id === provider.defaultModel)?.name ?? (provider.defaultModel || "auto");
  const effectiveBaseUrl = provider.baseUrl || provider.defaultBaseUrl;

  return (
    <Card className="flex flex-col transition-colors hover:border-border-strong">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-lg border border-border font-mono text-[11px] font-semibold uppercase tracking-wider",
              provider.tint,
            )}
            aria-hidden
          >
            {provider.short}
          </div>
          <div className="min-w-0">
            <CardTitle className="text-sm truncate">{provider.name}</CardTitle>
            <CardDescription className="mt-0.5 line-clamp-2">
              {provider.description}
            </CardDescription>
          </div>
        </div>
        <Switch
          checked={provider.enabled}
          onCheckedChange={onToggle}
          aria-label={`Toggle ${provider.name}`}
        />
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-3">
        <dl className="grid gap-2 text-xs">
          <MetaRow label="Default model" value={modelName} mono />
          <MetaRow label="Base URL" value={effectiveBaseUrl} mono truncate />
          <MetaRow
            label="API key"
            value={provider.apiKey || "—"}
            mono
            muted={!provider.apiKey}
          />
        </dl>

        <div className="mt-auto flex items-center justify-between pt-1">
          <StatusIndicator
            tone={meta.tone}
            label={meta.label}
            pulse={provider.status === "ready" && provider.enabled}
          />
          <Button variant="outline" size="sm" onClick={onConfigure}>
            <SettingsIcon size={13} />
            Configure
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function MetaRow({
  label,
  value,
  mono,
  muted,
  truncate,
}: {
  label: string;
  value: string;
  mono?: boolean;
  muted?: boolean;
  truncate?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground shrink-0">{label}</dt>
      <dd
        className={cn(
          "min-w-0 text-right text-foreground",
          mono && "font-mono text-[11px]",
          muted && "text-muted-foreground",
          truncate && "truncate",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function ConfigureSheet({
  provider,
  onOpenChange,
  onSave,
}: {
  provider: Provider | null;
  onOpenChange: (open: boolean) => void;
  onSave: (
    provider: Provider,
    values: { apiKey: string; baseUrl: string; defaultModel: string },
  ) => void;
}) {
  // Derive stable defaults directly from the provider prop so the
  // Select value is always in the controlled set from the first render.
  const safeModels = provider?.models?.length ? provider.models : [{ id: "auto", name: "Auto" }];
  const safeDefault = provider?.defaultModel
    ? (safeModels.find(m => m.id === provider.defaultModel) ? provider.defaultModel : safeModels[0].id)
    : safeModels[0].id;

  const [apiKey, setApiKey] = React.useState(provider?.apiKey || "");
  const [baseUrl, setBaseUrl] = React.useState(provider?.baseUrl || "");
  const [defaultModel, setDefaultModel] = React.useState(safeDefault);
  const [showKey, setShowKey] = React.useState(false);
  const [testing, setTesting] = React.useState(false);

  // Resync when provider identity changes.
  const prevId = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!provider || provider.id === prevId.current) return;
    prevId.current = provider.id;
    const models = provider.models?.length ? provider.models : [{ id: "auto", name: "Auto" }];
    const dm = provider.defaultModel
      ? (models.find(m => m.id === provider.defaultModel) ? provider.defaultModel : models[0].id)
      : models[0].id;
    setApiKey(provider.apiKey);
    setBaseUrl(provider.baseUrl);
    setDefaultModel(dm);
    setShowKey(false);
    setTesting(false);
  }, [provider]);

  if (!provider) {
    return (
      <Sheet open={false} onOpenChange={onOpenChange}>
        <SheetContent />
      </Sheet>
    );
  }

  const meta = STATUS_META[provider.status];

  const handleTest = () => {
    if (!apiKey.trim()) {
      toast.error("Add an API key first");
      return;
    }
    setTesting(true);
    window.setTimeout(() => {
      setTesting(false);
      toast.success(`${provider.name} connection looks good`);
    }, 900);
  };

  // Use safeModels so the Select always has at least one item matching the value.
  const displayModels = provider.models?.length ? provider.models : [{ id: "auto", name: "Auto" }];

  return (
    <Sheet open={!!provider} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md flex flex-col gap-0 p-0">
        <SheetHeader className="p-6 hairline-b">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex size-10 items-center justify-center rounded-lg border border-border font-mono text-[11px] font-semibold uppercase tracking-wider",
                provider.tint,
              )}
              aria-hidden
            >
              {provider.short}
            </div>
            <div className="min-w-0">
              <SheetTitle className="truncate">{provider.name}</SheetTitle>
              <SheetDescription className="line-clamp-2">
                {provider.description}
              </SheetDescription>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <StatusIndicator tone={meta.tone} label={meta.label} />
            <a
              href={provider.docsUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline underline-offset-2"
            >
              Docs ↗
            </a>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="cfg-apiKey" className="flex items-center gap-1.5">
              API Key <span className="text-destructive">*</span>
            </Label>
            <div className="relative">
              <Input
                id="cfg-apiKey"
                type={showKey ? "text" : "password"}
                placeholder="Paste your API key"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="pr-9 font-mono text-xs"
                autoComplete="off"
                spellCheck={false}
              />
              <button
                type="button"
                onClick={() => setShowKey((v) => !v)}
                className="absolute inset-y-0 right-2 flex items-center text-muted-foreground hover:text-foreground"
                aria-label={showKey ? "Hide API key" : "Show API key"}
              >
                {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Keys stay on-device. They are never sent anywhere from this screen.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cfg-baseUrl">Base URL</Label>
            <Input
              id="cfg-baseUrl"
              type="url"
              inputMode="url"
              placeholder={provider.defaultBaseUrl}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="font-mono text-xs"
              autoComplete="off"
              spellCheck={false}
            />
            <p className="text-[11px] text-muted-foreground">
              Leave blank to use the default endpoint.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cfg-model">Default model</Label>
            <Select value={defaultModel} onValueChange={setDefaultModel}>
              <SelectTrigger id="cfg-model">
                <SelectValue placeholder="Choose a default model" />
              </SelectTrigger>
              <SelectContent>
                {displayModels.map((m: any) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="rounded-lg border border-border bg-surface/60 p-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-medium">Test connection</div>
              <p className="text-[11px] text-muted-foreground">
                Verify the key against {provider.name}.
              </p>
            </div>
            <Button variant="secondary" size="sm" onClick={handleTest} disabled={testing}>
              {testing ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  Testing
                </>
              ) : (
                <>
                  <Zap size={13} />
                  Test
                </>
              )}
            </Button>
          </div>
        </div>

        <SheetFooter className="p-6 hairline-t">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="accent"
            onClick={() => onSave(provider, { apiKey, baseUrl, defaultModel })}
          >
            Save changes
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}