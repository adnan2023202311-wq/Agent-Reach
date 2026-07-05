import * as React from "react";
import type {
  ProviderOption,
  ModelOption,
} from "@/components/layout/provider-selector";
import { providersService } from "@/services";

/**
 * Global topbar (provider + model) state.
 *
 * Extracted so every route wires the same six props into `AppShell` with
 * a single spread. When application-wide topbar state moves out of local
 * `useState` (e.g. into a store or query), this is the only place to change.
 */
export interface TopbarState {
  providers: ProviderOption[];
  models: ModelOption[];
  activeProvider: ProviderOption;
  activeModel: ModelOption;
  onProviderChange: (p: ProviderOption) => void;
  onModelChange: (m: ModelOption) => void;
}

// Cached at module scope so we don't rebuild the list on every render.
const providers = providersService.topbarProviders();
const models = providersService.topbarModels();

export function useTopbar(): TopbarState {
  const [activeProvider, onProviderChange] = React.useState<ProviderOption>(providers[0]);
  const [activeModel, onModelChange] = React.useState<ModelOption>(models[0]);
  return { providers, models, activeProvider, activeModel, onProviderChange, onModelChange };
}
