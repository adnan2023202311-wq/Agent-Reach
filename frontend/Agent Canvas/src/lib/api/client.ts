/**
 * Minimal fetch-based API client.
 *
 * Production path: all core pages (Dashboard, Chat, Agents, Tools, Providers)
 * route through `src/services/http/index.ts` which calls this client to reach
 * the FastAPI backend. Workspace pages (Agent Studio, Knowledge, Playground,
 * Prompts, Memory, Workflows, Observatory, Marketplace) call `api.get/post/…`
 * directly.
 *
 * In development a `.env` file sets `VITE_API_MODE=http` and
 * `VITE_API_BASE_URL=http://localhost:8000`. To work offline set
 * `VITE_API_MODE=mock`.
 *
 * Configuration:
 *   - `VITE_API_BASE_URL`  base URL of the FastAPI server
 *   - `VITE_API_MODE`      "http" (default) | "mock"
 */

import { ApiError, type ApiErrorBody } from "./types";

const BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  query?: Query;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(
    path.startsWith("http") ? path : `${BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`,
    // Fallback origin lets us build URLs when BASE_URL is empty (e.g. in tests).
    typeof window === "undefined" ? "http://localhost" : window.location.origin,
  );
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === null || value === undefined) continue;
      url.searchParams.set(key, String(value));
    }
  }
  return BASE_URL || path.startsWith("http") ? url.toString() : url.pathname + url.search;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...options.headers,
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(buildUrl(path, options.query), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: options.signal,
  });

  if (!response.ok) {
    let payload: ApiErrorBody = { message: response.statusText || "Request failed" };
    try {
      const parsed = (await response.json()) as Partial<ApiErrorBody>;
      if (parsed && typeof parsed === "object") {
        payload = { message: parsed.message ?? payload.message, code: parsed.code, details: parsed.details };
      }
    } catch {
      // Response body was not JSON — keep the default payload.
    }
    throw new ApiError(response.status, payload);
  }

  // 204 No Content
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("POST", path, body, options),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PUT", path, body, options),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PATCH", path, body, options),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>("DELETE", path, undefined, options),
};

export type ApiClient = typeof api;
