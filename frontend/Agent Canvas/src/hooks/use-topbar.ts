import * as React from "react";
import type { ProviderOption, ModelOption } from "@/components/layout/provider-selector";
import { providersService } from "@/services";

export interface TopbarState {
  providers: ProviderOption[];
  models: ModelOption[];
  activeProvider: ProviderOption;
  activeModel: ModelOption;
  onProviderChange: (p: ProviderOption) => void;
  onModelChange: (m: ModelOption) => void;
}

const FALLBACK_PROVIDERS: ProviderOption[] = [
  { id: "anthropic", name: "Anthropic", tint: "bg-[#d97757]/15 text-[#d97757]" },
  { id: "openai",   name: "OpenAI",   tint: "bg-[#74aa9c]/15 text-[#74aa9c]" },
  { id: "google",   name: "Google",   tint: "bg-[#4285f4]/15 text-[#4285f4]" },
  { id: "deepseek", name: "DeepSeek", tint: "bg-[#3b82f6]/15 text-[#3b82f6]" },
  { id: "groq",     name: "Groq",     tint: "bg-[#f97316]/15 text-[#f97316]" },
  { id: "openrouter", name: "OpenRouter", tint: "bg-[#a855f7]/15 text-[#a855f7]" },
];
const FALLBACK_MODELS: ModelOption[] = [
  { id: "anthropic:claude-sonnet-5", name: "Claude Sonnet 5", providerId: "anthropic" },
];

export function useTopbar(): TopbarState {
  const [providers, setProviders] = React.useState<ProviderOption[]>(FALLBACK_PROVIDERS);
  const [models, setModels] = React.useState<ModelOption[]>(FALLBACK_MODELS);
  const [activeProvider, setActiveProvider] = React.useState<ProviderOption>(FALLBACK_PROVIDERS[0]);
  const [activeModel, setActiveModel] = React.useState<ModelOption>(FALLBACK_MODELS[0]);

  // Fetch live providers/models from backend on mount.
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await providersService.list();
        if (cancelled || !list?.length) return;

        const liveProviders: ProviderOption[] = [];
        const liveModels: ModelOption[] = [];
        for (const p of list) {
          if (!p?.id) continue;
          liveProviders.push({
            id: p.id,
            name: p.name || p.id,
            tint: _tintFor(p.id),
            status: p.enabled ? "ready" as const : "unconfigured" as const,
          });
          const raw: any[] = Array.isArray(p.models) ? p.models : [];
          for (const m of raw) {
            if (m == null) continue;
            if (typeof m === "string") {
              liveModels.push({ id: `${p.id}:${m}`, name: m, providerId: p.id });
            } else if (typeof m === "object") {
              const mid = m.id || m.name || "";
              if (mid) liveModels.push({ id: `${p.id}:${mid}`, name: m.name || mid, providerId: p.id });
            }
          }
        }

        if (liveProviders.length > 0) {
          setProviders(liveProviders);
          // Visible dev logs so the "only Anthropic shows" bug can be
          // diagnosed at a glance. These confirm useTopbar DID receive
          // the full live list from /api/v1/providers.
          // eslint-disable-next-line no-console
          console.info(
            `[useTopbar] fetched ${liveProviders.length} providers:`,
            liveProviders.map(p => p.id).join(", "),
          );
          // eslint-disable-next-line no-console
          console.info(
            `[useTopbar] Built ${liveProviders.length} provider options`,
          );
        }
        if (liveModels.length > 0) {
          setModels(liveModels);
          // eslint-disable-next-line no-console
          console.info(
            `[useTopbar] Built ${liveModels.length} model options`,
          );
          // Default to Anthropic if available, else first provider's first model.
          const def = liveModels.find(m => m.providerId === "anthropic") || liveModels[0];
          setActiveModel(def);
          setActiveProvider(liveProviders.find(p => p.id === def.providerId) || liveProviders[0]);
          // eslint-disable-next-line no-console
          console.info(
            `[useTopbar] activeProvider=${def.providerId}, activeModel=${def.id}, providers array length=${liveProviders.length}`,
          );
        }
      } catch { /* keep fallbacks */ }
    })();
    return () => { cancelled = true; };
  }, []);

  // Simple inline callbacks — no useCallback, no refs.
  // Each render creates fresh closures with the CURRENT models/activeProvider
  // values. React passes these new functions to ProviderSelector/ModelSelector
  // which correctly receive the latest state.
  function handleProviderChange(p: ProviderOption) {
    setActiveProvider(p);
    const filtered = models.filter(m => m.providerId === p.id);
    if (filtered.length > 0) setActiveModel(filtered[0]);
  }

  function handleModelChange(m: ModelOption) {
    setActiveModel(m);
  }

  return {
    providers,
    models,
    activeProvider,
    activeModel,
    onProviderChange: handleProviderChange,
    onModelChange: handleModelChange,
  };
}

function _tintFor(id: string): string {
  const map: Record<string, string> = {
    anthropic:  "bg-[#d97757]/15 text-[#d97757]",
    openai:     "bg-[#74aa9c]/15 text-[#74aa9c]",
    google:     "bg-[#4285f4]/15 text-[#4285f4]",
    openrouter: "bg-[#a855f7]/15 text-[#a855f7]",
    deepseek:   "bg-[#3b82f6]/15 text-[#3b82f6]",
    groq:       "bg-[#f97316]/15 text-[#f97316]",
  };
  return map[id] || "bg-accent/15 text-accent";
}
