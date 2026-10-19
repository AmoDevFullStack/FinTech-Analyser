import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "@/api/client";
import { clearTokens, storeTokens } from "@/api/tokens";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function errorResponse(code: string, status: number, details: unknown = {}): Response {
  return jsonResponse({ error: { code, message: "nope", details } }, status);
}

const fetchMock = vi.fn();

function lastRequestHeaders(callIndex: number): Headers {
  return new Headers(fetchMock.mock.calls[callIndex][1].headers as HeadersInit);
}

describe("api client", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearTokens();
  });

  it("sends no Authorization header when there is no token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await api.get("/position");

    expect(lastRequestHeaders(0).has("Authorization")).toBe(false);
  });

  it("attaches the access token as a bearer credential", async () => {
    storeTokens({
      access_token: "access-1",
      refresh_token: "refresh-1",
      token_type: "Bearer",
      expires_in: 900,
    });
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await api.get("/position");

    expect(lastRequestHeaders(0).get("Authorization")).toBe("Bearer access-1");
  });

  it("keeps sending the session cookie alongside the token", async () => {
    // Both credentials are supported on purpose — see backend/app/core/auth.py. Dropping
    // the cookie would break the Playwright suite, which authenticates with it.
    storeTokens({
      access_token: "access-1",
      refresh_token: "refresh-1",
      token_type: "Bearer",
      expires_in: 900,
    });
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await api.get("/position");

    expect(fetchMock.mock.calls[0][1].credentials).toBe("include");
  });

  it("refreshes once and retries after a 401", async () => {
    storeTokens({
      access_token: "stale",
      refresh_token: "refresh-1",
      token_type: "Bearer",
      expires_in: 900,
    });
    fetchMock
      .mockResolvedValueOnce(errorResponse("unauthenticated", 401))
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "access-2",
          refresh_token: "refresh-2",
          token_type: "Bearer",
          expires_in: 900,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    await expect(api.get("/position")).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/auth/refresh");
    expect(lastRequestHeaders(2).get("Authorization")).toBe("Bearer access-2");
  });

  it("performs one refresh for several requests that all hit a 401 at once", async () => {
    // The backend rotates and revokes the presented refresh token, so a page that fires
    // six queries against an expired access token and refreshes six times would log the
    // user out with its own page load.
    storeTokens({
      access_token: "stale",
      refresh_token: "refresh-1",
      token_type: "Bearer",
      expires_in: 900,
    });
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes("/auth/refresh")) {
        return Promise.resolve(
          jsonResponse({
            access_token: "access-2",
            refresh_token: "refresh-2",
            token_type: "Bearer",
            expires_in: 900,
          }),
        );
      }
      const header = new Headers(
        (fetchMock.mock.calls.at(-1)?.[1]?.headers ?? {}) as HeadersInit,
      );
      return Promise.resolve(
        header.get("Authorization") === "Bearer access-2"
          ? jsonResponse({ ok: true })
          : errorResponse("unauthenticated", 401),
      );
    });

    await Promise.all([api.get("/position"), api.get("/debts"), api.get("/goals")]);

    const refreshCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes("/auth/refresh"),
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it("gives up and clears the tokens when the refresh itself is rejected", async () => {
    storeTokens({
      access_token: "stale",
      refresh_token: "expired",
      token_type: "Bearer",
      expires_in: 900,
    });
    fetchMock
      .mockResolvedValueOnce(errorResponse("unauthenticated", 401))
      .mockResolvedValueOnce(errorResponse("unauthenticated", 401));

    await expect(api.get("/position")).rejects.toBeInstanceOf(ApiError);

    expect(window.sessionStorage.getItem("fdt.refresh_token")).toBeNull();
  });

  it("does not try to refresh when there is no refresh token", async () => {
    fetchMock.mockResolvedValue(errorResponse("unauthenticated", 401));

    await expect(api.get("/position")).rejects.toBeInstanceOf(ApiError);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refreshes ahead of a request when the stored expiry has passed", async () => {
    storeTokens({
      access_token: "about-to-die",
      refresh_token: "refresh-1",
      token_type: "Bearer",
      // Already inside the refresh skew, so the client refreshes before it sends anything
      // rather than spending a guaranteed round trip on a 401.
      expires_in: 0,
    });
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "access-2",
          refresh_token: "refresh-2",
          token_type: "Bearer",
          expires_in: 900,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    await api.get("/position");

    expect(fetchMock.mock.calls[0][0]).toContain("/auth/refresh");
    expect(lastRequestHeaders(1).get("Authorization")).toBe("Bearer access-2");
  });

  it("surfaces the backend's field errors on a validation failure", async () => {
    // A fresh Response per call: a Response body can only be read once, so reusing one
    // across two awaits fails on the second with a TypeError that looks nothing like the
    // thing being tested.
    fetchMock.mockImplementation(() =>
      Promise.resolve(errorResponse("validation_error", 400, { fields: { limit: "too large" } })),
    );

    const error = await api.get("/transactions?limit=99999").catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(400);
    expect((error as ApiError).code).toBe("validation_error");
    expect((error as ApiError).fieldErrors).toEqual({ limit: "too large" });
  });

  it("does not set a Content-Type on a multipart upload", async () => {
    // The browser writes it, including the boundary. Setting it by hand produces a
    // boundary-less header the server cannot parse.
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    const form = new FormData();
    form.append("account_id", "abc");

    await api.postForm("/imports", form);

    expect(lastRequestHeaders(0).has("Content-Type")).toBe(false);
  });

  it("fails loudly on a non-JSON success response", async () => {
    fetchMock.mockResolvedValue(
      new Response("<!doctype html>", { status: 200, headers: { "content-type": "text/html" } }),
    );

    await expect(api.get("/position")).rejects.toMatchObject({ code: "unexpected_response" });
  });
});
