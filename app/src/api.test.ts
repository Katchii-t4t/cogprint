import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

/**
 * Guardrail #5 — never enumerate, and never put a secret in a URL.
 *
 * This product already shipped an id-addressed account restore once. The tests
 * here pin the shape of the replacement: secrets travel in the request body,
 * where they stay out of access logs, browser history and Referer headers.
 */

let fetchMock: ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: "OK",
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

/** The URL of call `n`, as a string, regardless of how fetch was invoked. */
function calledUrl(n = 0): string {
  return String(fetchMock.mock.calls[n][0]);
}

function calledBody(n = 0): Record<string, unknown> {
  const init = fetchMock.mock.calls[n][1] as RequestInit;
  return JSON.parse(String(init.body));
}

beforeEach(() => {
  fetchMock = vi.fn(async () => jsonResponse({}));
  vi.stubGlobal("fetch", fetchMock);
});

describe("secrets never travel in the URL", () => {
  const SECRET = "b8f2c1a09d4e7f36b8f2c1a09d4e7f36b8f2c1a09d4e7f36";

  it("sends the recovery token in the body, not the path or query", async () => {
    await api.recoverAccount(SECRET);
    expect(calledUrl()).toBe("/api/auth/recover");
    expect(calledUrl()).not.toContain(SECRET);
    expect(calledBody()).toEqual({ recovery_token: SECRET });
  });

  it("sends the rotation-time attach token in the body too", async () => {
    await api.attachEmail(SECRET, "someone@example.com");
    expect(calledUrl()).not.toContain(SECRET);
    expect(calledUrl()).not.toContain("someone");
    expect(calledBody()).toEqual({
      recovery_token: SECRET,
      email: "someone@example.com",
    });
  });

  it("sends the magic-link email and verification token in the body", async () => {
    await api.requestMagicLink("someone@example.com");
    expect(calledUrl()).toBe("/api/auth/magic-link/request");
    expect(calledUrl()).not.toContain("someone@example.com");

    fetchMock.mockClear();
    await api.verifyMagicLink("magic-token-123");
    expect(calledUrl()).not.toContain("magic-token-123");
    expect(calledBody()).toEqual({ token: "magic-token-123" });
  });

  it("exposes no account lookup addressed by a bare user id", async () => {
    // The removed endpoint was a GET that returned another user's account when
    // handed their (sequential) id. Nothing in the client should reintroduce a
    // call whose only argument is an id and whose result is an identity.
    expect(api).not.toHaveProperty("restoreAccount");
    expect(api).not.toHaveProperty("getUser");
  });
});

describe("request construction", () => {
  it("creates a user by group in the body", async () => {
    await api.createUser("control");
    expect(calledUrl()).toBe("/api/users");
    expect(calledBody()).toEqual({ group: "control" });
  });

  it("asks for questions with POST, because the endpoint generates and caches", async () => {
    await api.getQuestions(4, 12);
    expect(calledUrl()).toBe("/api/materials/4/questions?n=12");
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("POST");
  });

  it("passes the plan horizon through as a query parameter", async () => {
    await api.getStudyPlan(3, 9, 21);
    const url = new URL(calledUrl(), "http://localhost");
    expect(url.pathname).toBe("/api/users/3/study-plan");
    expect(url.searchParams.get("material_id")).toBe("9");
    expect(url.searchParams.get("total_days")).toBe("21");
  });

  it("defaults the plan to fourteen days", async () => {
    await api.getStudyPlan(3, 9);
    expect(calledUrl()).toContain("total_days=14");
  });

  it("normalises a buddy code the user typed in lower case", async () => {
    // Share codes are read off a screen and retyped. Case-folding client-side
    // avoids a "code not found" for a code that is right.
    await api.getBuddyForecast("ab12cd");
    expect(calledUrl()).toBe("/api/buddy/AB12CD/forecast");
  });

  it("logs the technique the round actually used", async () => {
    await api.logSession({
      user_id: 1,
      material_id: 2,
      technique: "practice_testing",
      duration_minutes: 25,
      time_of_day: "morning",
      quiz_score: 0.8,
    });
    expect(calledBody().technique).toBe("practice_testing");
  });
});

describe("error handling", () => {
  it("throws with the status code so callers can distinguish 404 from 500", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "nope" }, { ok: false, status: 404 })
    );
    await expect(api.getFingerprint(1)).rejects.toThrow(/404/);
  });

  it("still throws when the error body is not readable", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      text: async () => {
        throw new Error("stream already consumed");
      },
      json: async () => ({}),
    });
    await expect(api.getFingerprint(1)).rejects.toThrow(/503/);
  });

  it("propagates a network failure rather than resolving with nothing", async () => {
    // A silently-resolved undefined would render an empty screen that looks
    // like "you have no data" instead of "we couldn't reach the server".
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(api.getFingerprint(1)).rejects.toThrow(/Failed to fetch/);
  });
});
