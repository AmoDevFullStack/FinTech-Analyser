/** The only place `fetch` happens — see docs/frontend.md §3.1. */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function handle<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    // A non-JSON 2xx (Vite's dev-server SPA fallback returning index.html for an
    // unproxied /api path is the case that bit us locally) must fail loudly, not be
    // silently treated as an empty success payload — that masked a real crash instead of
    // surfacing a wiring problem. See vite.config.ts's dev proxy for the actual fix.
    throw new ApiError(
      response.status,
      "unexpected_response",
      `Expected JSON from ${response.url}, got "${contentType || "unknown"}".`,
      {},
    );
  }

  const body = await response.json();
  if (!response.ok) {
    const envelope = body?.error ?? { code: "unknown", message: "Request failed" };
    throw new ApiError(response.status, envelope.code, envelope.message, envelope.details ?? {});
  }
  return body as T;
}

export const api = {
  get<T>(path: string): Promise<T> {
    return fetch(`${BASE_URL}${path}`, { credentials: "include" }).then((r) => handle<T>(r));
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return fetch(`${BASE_URL}${path}`, {
      method: "POST",
      credentials: "include",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then((r) => handle<T>(r));
  },
  patch<T>(path: string, body?: unknown): Promise<T> {
    return fetch(`${BASE_URL}${path}`, {
      method: "PATCH",
      credentials: "include",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then((r) => handle<T>(r));
  },
  postForm<T>(path: string, form: FormData): Promise<T> {
    return fetch(`${BASE_URL}${path}`, {
      method: "POST",
      credentials: "include",
      body: form,
    }).then((r) => handle<T>(r));
  },
  delete<T>(path: string): Promise<T> {
    return fetch(`${BASE_URL}${path}`, { method: "DELETE", credentials: "include" }).then((r) =>
      handle<T>(r),
    );
  },
};
