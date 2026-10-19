/**
 * Where the JWT pair lives in the browser. See backend/app/core/tokens.py for what the
 * two tokens are and why their lifetimes differ.
 *
 * On storage: `sessionStorage`, not `localStorage`. The backend still issues its
 * `HttpOnly` session cookie and this client still sends it, so the tokens are the
 * *second* credential rather than the only one — which means the security question is
 * not "can we make a browser token as safe as a cookie" (we cannot; any script on the
 * page can read either store) but "how long does a readable copy survive". `sessionStorage`
 * is scoped to the tab and cleared when it closes; `localStorage` would leave a
 * thirty-day refresh token on a shared machine indefinitely.
 *
 * Every access is wrapped: Safari in private mode throws on `sessionStorage` access
 * rather than returning null, and an app that cannot log in at all in a private window is
 * a worse outcome than one that falls back to the cookie.
 */

const ACCESS_KEY = "fdt.access_token";
const REFRESH_KEY = "fdt.refresh_token";
const EXPIRY_KEY = "fdt.access_expires_at";

/** Refresh this many milliseconds before the access token actually expires. Covers the
 * round trip and a slow connection, so a request is never sent with a token that dies
 * in flight. */
const REFRESH_SKEW_MS = 30_000;

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

function read(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Storage unavailable (private mode, blocked cookies). The session cookie still
    // authenticates this session; it just will not survive a page reload.
  }
}

function remove(key: string): void {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    /* see write() */
  }
}

export function storeTokens(pair: TokenPair): void {
  write(ACCESS_KEY, pair.access_token);
  write(REFRESH_KEY, pair.refresh_token);
  write(EXPIRY_KEY, new Date(Date.now() + pair.expires_in * 1000).toISOString());
}

export function clearTokens(): void {
  remove(ACCESS_KEY);
  remove(REFRESH_KEY);
  remove(EXPIRY_KEY);
}

export function accessToken(): string | null {
  return read(ACCESS_KEY);
}

export function refreshToken(): string | null {
  return read(REFRESH_KEY);
}

/** Whether the access token is close enough to expiry to be refreshed before the next call.
 *
 * An unknown expiry counts as "not yet" rather than "now": a token we cannot date is
 * either absent, in which case there is nothing to refresh, or stored by an older build,
 * in which case the 401 path will handle it.
 */
export function accessTokenIsStale(): boolean {
  const raw = read(EXPIRY_KEY);
  if (raw === null) return false;
  // Stored as an ISO instant and read with `Date.parse`, which is both the honest type for
  // a point in time and keeps this file clear of the numeric narrowing that
  // src/lib/money.ts owns (docs/frontend.md §4).
  const expiresAt = Date.parse(raw);
  if (Number.isNaN(expiresAt)) return false;
  return Date.now() >= expiresAt - REFRESH_SKEW_MS;
}
