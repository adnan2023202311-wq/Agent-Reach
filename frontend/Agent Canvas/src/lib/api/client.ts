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
 *
 * IMPORTANT — buildUrl precedence bug fix (v2.2):
 *   The previous `buildUrl()` had a JS operator-precedence bug that returned
 *   relative paths when BASE_URL was empty, causing `fetch("/api/...")` to
 *   hit the frontend Vite/Nitro server instead of FastAPI. Fixed by always
 *   building absolute URLs with a DEFAULT_BACKEND_URL fallback.
 */

import { ApiError, type ApiErrorBody } from "./types";

// Hardcoded fallback — the documented FastAPI backend default. Used only
// when VITE_API_BASE_URL is unset. Never derived from window.location
// (that origin is the frontend server, the source of the bug).
const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

const BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ||
  DEFAULT_BACKEND_URL;

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  query?: Query;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Query): string {
  // If the caller already passed a full URL, use it as-is.
  if (path.startsWith("http")) {
    const u = new URL(path);
    if (query) {
      for (const [k, v] of Object.entries(query)) {
        if (v === null || v === undefined) continue;
        u.searchParams.set(k, String(v));
      }
    }
    return u.toString();
  }

  // Normalize: ensure leading slash so URL construction is predictable.
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  // Always build against BASE_URL (which is either the user-set value
  // or the DEFAULT_BACKEND_URL). Never return a relative path — that's
  // the bug we're fixing.
  const u = new URL(`${BASE_URL}${normalizedPath}`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === null || v === undefined) continue;
      u.searchParams.set(k, String(v));
    }
  }
  return u.toString();
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
