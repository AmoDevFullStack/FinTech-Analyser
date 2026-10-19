/** The only place `fetch` happens — see docs/frontend.md §3.1. */

import {
  accessToken,
  accessTokenIsStale,
  clearTokens,
  refreshToken,
  storeTokens,
  type TokenPair,
} from "@/api/tokens";

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

  /** Field-level messages from the backend's validation envelope, when it sent any.
   * `details.fields` is `{field: reason}` — see backend/app/schemas/base.py. */
  get fieldErrors(): Record<string, string> {
    const fields = this.details.fields;
    return typeof fields === "object" && fields !== null
      ? (fields as Record<string, string>)
      : {};
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

/**
 * A single in-flight refresh, shared by every caller that needs one.
 *
 * Without this, a dashboard that fires six queries at once against an expired access
 * token performs six refreshes. Five of them would then present a token the first one had
 * already rotated and revoked (see backend/app/core/tokens.py), and the user would be
 * logged out by their own page load.
 */
let inFlightRefresh: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const token = refreshToken();
  if (token === null) return false;

  if (inFlightRefresh === null) {
    inFlightRefresh = (async () => {
      try {
        const response = await fetch(`${BASE_URL}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: token }),
        });
        if (!response.ok) {
          clearTokens();
          return false;
        }
        storeTokens((await response.json()) as TokenPair);
        return true;
      } catch {
        // A network failure is not an authentication failure. Keeping the tokens means a
        // reconnecting client resumes instead of being signed out by a dropped request.
        return false;
      } finally {
        inFlightRefresh = null;
      }
    })();
  }

  return inFlightRefresh;
}

function authHeaders(extra?: HeadersInit): HeadersInit | undefined {
  const token = accessToken();
  if (token === null) return extra;
  return { ...(extra ?? {}), Authorization: `Bearer ${token}` };
}

/**
 * Send the request, refreshing the access token around it where that is what is wrong.
 *
 * Two refresh points, and both are needed. Before the call, when the stored expiry says
 * the token is about to die — that avoids a guaranteed round trip into a 401. After a 401,
 * because a token can be rejected for reasons the client cannot see: the server clock, a
 * restart with a rotated signing key, a token revoked elsewhere.
 *
 * `credentials: "include"` stays on every request. The session cookie is still a valid
 * credential and still what the Playwright suite authenticates with.
 */
async function send<T>(path: string, init: RequestInit, headers?: HeadersInit): Promise<T> {
  if (accessTokenIsStale()) {
    await refreshAccessToken();
  }

  const request = () =>
    fetch(`${BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: authHeaders(headers),
    });

  let response = await request();
  if (response.status === 401 && refreshToken() !== null) {
    if (await refreshAccessToken()) {
      response = await request();
    }
  }

  return handle<T>(response);
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export const api = {
  get<T>(path: string): Promise<T> {
    return send<T>(path, { method: "GET" });
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return send<T>(
      path,
      { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined },
      body !== undefined ? JSON_HEADERS : undefined,
    );
  },
  patch<T>(path: string, body?: unknown): Promise<T> {
    return send<T>(
      path,
      { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined },
      body !== undefined ? JSON_HEADERS : undefined,
    );
  },
  postForm<T>(path: string, form: FormData): Promise<T> {
    // No Content-Type header: the browser sets it, including the multipart boundary, and
    // setting it by hand produces a boundary-less header the server cannot parse.
    return send<T>(path, { method: "POST", body: form });
  },
  delete<T>(path: string): Promise<T> {
    return send<T>(path, { method: "DELETE" });
  },
};
