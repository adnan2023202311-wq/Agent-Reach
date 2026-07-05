/**
 * Mock providers service — reads from `@/features/providers/data`.
 * Async methods return resolved promises so callers can migrate to
 * TanStack Query without changing signatures.
 */

import {
  providersData,
  providerCatalog,
  topbarProviders,
  topbarModels,
  type Provider,
} from "@/features/providers/data";
import type { ProvidersService } from "@/services/types";

export const providersMockService: ProvidersService = {
  list: async () => providersData,
  listSync: () => providersData,
  catalog: async () => providerCatalog,
  catalogSync: () => providerCatalog,
  topbarProviders: () => topbarProviders,
  topbarModels: () => topbarModels,
  update: async (id: string, patch: Partial<Provider>) => {
    const idx = providersData.findIndex((p) => p.id === id);
    if (idx === -1) throw new Error(`Provider "${id}" not found`);
    const next = { ...providersData[idx], ...patch };
    providersData[idx] = next;
    return next;
  },
};
