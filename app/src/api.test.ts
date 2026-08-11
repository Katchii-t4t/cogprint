import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { setState } from "./store";

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

describe("the credential", () => {
  const SAVED = "b8f2c1a09d4e7f36b8f2c1a09d4e7f36b8f2c1a09d4e7f36";

  function headersOf(n = 0): Record<string, string> {
    return (fetchMock.mock.calls[n][1] as RequestInit).headers as Record<string, string>;
  }

  it("attaches the stored recovery key to every request", async () => {
    // Every route addressed by user_id requires it. Without this the app
    // silently 401s on the library, the plan and the fingerprint.
    setState({ userId: 3, recoveryKey: SAVED });
    await api.getFingerprint(3);
    expect(headersOf().Authorization).toBe(`Bearer ${SAVED}`);
  });

  it("sends no Authorization header when there is no key yet", async () => {
    // Sign-up itself is unauthenticated; sending `Bearer null` would be worse
    // than sending nothing, because it looks like a failed credential.
    await api.createUser("treatment");
    expect(headersOf()).not.toHaveProperty("Authorization");
  });

  it("picks up a rotated key without a reload", async () => {
    // Rotation replaces the token mid-session. A value captured once at module
    // load would log the user out until they refreshed.
    setState({ userId: 3, recoveryKey: SAVED });
    await api.getFingerprint(3);
    setState({ recoveryKey: "rotated-token" });
    await api.getFingerprint(3);
    expect(headersOf(1).Authorization).toBe("Bearer rotated-token");
  });

  it("keeps the credential out of the URL", async () => {
    setState({ userId: 3, recoveryKey: SAVED });
    await api.getLibrary(3);
    expect(calledUrl()).not.toContain(SAVED);
  });

  it("does not let a caller-supplied init drop the headers", async () => {
    // `{headers, ...init}` let any init carrying its own headers replace the
    // whole object, credential included. Order matters here.
    setState({ userId: 3, recoveryKey: SAVED });
    await api.getQuestions(4);
    expect(headersOf().Authorization).toBe(`Bearer ${SAVED}`);
    expect(headersOf()["Content-Type"]).toBe("application/json");
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
  it("surfaces the server's message, not a JSON blob with a status glued on", async () => {
    // The user used to see, verbatim:
    //   422: {"detail":"Couldn't find anything to study in that text."}
    // — a perfectly good sentence buried in JSON and a status code, on the
    // front door of the product.
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "Couldn't find anything to study in that text." },
        { ok: false, status: 422 })
    );
    await expect(api.analyzeMaterial("t", "...")).rejects.toThrow(
      "Couldn't find anything to study in that text."
    );
  });

  it("carries the status so callers can branch without parsing prose", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "nope" }, { ok: false, status: 404 })
    );
    await expect(api.getFingerprint(1)).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
    });
  });

  it("does not show a validation error list to the user", async () => {
    // FastAPI's 422 body is a list of field errors — useful in a log, useless
    // and alarming on screen.
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: [{ loc: ["body", "raw_text"], msg: "too long" }] },
        { ok: false, status: 422 })
    );
    await expect(api.analyzeMaterial("t", "x")).rejects.toThrow(/wasn't valid/);
  });

  it("falls back to something sayable when the body is not JSON", async () => {
    // A proxy or gateway error page, which is HTML.
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      text: async () => "",
      json: async () => ({}),
    });
    await expect(api.getFingerprint(1)).rejects.toThrow("Bad Gateway");
  });

  it("still throws when the error body cannot be read at all", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      text: async () => {
        throw new Error("stream already consumed");
      },
      json: async () => ({}),
    });
    await expect(api.getFingerprint(1)).rejects.toMatchObject({ status: 503 });
  });

  it("propagates a network failure rather than resolving with nothing", async () => {
    // A silently-resolved undefined would render an empty screen that looks
    // like "you have no data" instead of "we couldn't reach the server".
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(api.getFingerprint(1)).rejects.toThrow(/Failed to fetch/);
  });
});
