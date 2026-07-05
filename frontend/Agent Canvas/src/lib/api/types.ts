/**
 * Shared HTTP / API response types.
 *
 * Kept transport-agnostic so both the mock service layer and the future
 * FastAPI-backed HTTP client can return values that satisfy the same
 * interfaces.
 */

/** Standard error envelope returned by the API client on non-2xx responses. */
export interface ApiErrorBody {
  message: string;
  code?: string;
  details?: unknown;
}

/** Thrown by the API client for non-2xx HTTP responses. */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details?: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

/** Cursor / offset paginated envelope, ready for list endpoints. */
export interface Paginated<T> {
  items: T[];
  total: number;
  page?: number;
  pageSize?: number;
  nextCursor?: string | null;
}

/** Generic acknowledgement returned by mutation endpoints. */
export interface Ack {
  ok: true;
  id?: string;
}
