import { afterEach, describe, expect, it, vi } from "vitest";
import {
  addRecent,
  clearState,
  currentHour,
  currentUserId,
  dismissNudge,
  getState,
  nudgeAllowed,
  setState,
} from "./store";

const KEY = "cogprint_app_v1";

/**
 * These target guardrail #4 — "don't lose users". Identity lives in one
 * localStorage key with no server-side session, so every way that key can be
 * malformed, stale or partially written is a way to strand someone outside
 * their own account. The tests below are that list.
 */

describe("getState", () => {
  it("survives corrupt JSON instead of crashing the app on boot", () => {
    // A truncated write (tab killed mid-quota-error) is the realistic cause.
    localStorage.setItem(KEY, '{"userId":7,"recents":[{"id"');
    expect(() => getState()).not.toThrow();
    expect(getState().userId).toBeNull();
  });

  it("fills in fields a state written by an older build never had", () => {
    // The regression this guards: `recents` was added after launch. A user who
    // installed before it existed has a stored object without the key, and
    // `getState().recents.filter(...)` in addRecent would throw on undefined —
    // bricking the paste flow for exactly the users who have been here longest.
    localStorage.setItem(KEY, JSON.stringify({ userId: 7, group: "treatment" }));
    const s = getState();
    expect(s.recents).toEqual([]);
    expect(s.recoveryKey).toBeNull();
    expect(() => addRecent(1, "Anything")).not.toThrow();
  });

  it("returns an empty state, not a shared one, when storage is untouched", () => {
    // Mutating the returned object must not poison the next read.
    const a = getState();
    a.recents.push({ id: 99, title: "mutated", ts: 0 });
    expect(getState().recents).toEqual([]);
  });
});

describe("setState", () => {
  it("patches without dropping the recovery key", () => {
    // Losing recoveryKey is unrecoverable: the server stores only a hash and
    // cannot re-issue it. Any write that silently replaces the whole object
    // permanently orphans the account.
    setState({ userId: 3, recoveryKey: "tok_abc", group: "control" });
    setState({ lastMaterialId: 12 });
    const s = getState();
    expect(s.recoveryKey).toBe("tok_abc");
    expect(s.userId).toBe(3);
    expect(s.group).toBe("control");
    expect(s.lastMaterialId).toBe(12);
  });

  it("does not throw when storage rejects the write", () => {
    // iOS Safari in private mode, and any browser at quota, throws from
    // setItem. Persisting the id is best-effort; crashing the caller is not an
    // acceptable failure mode, because the caller is the sign-up handler.
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new DOMException("QuotaExceededError");
      });
    expect(() => setState({ userId: 5 })).not.toThrow();
    spy.mockRestore();
  });
});

describe("addRecent", () => {
  it("moves a re-opened material to the front instead of duplicating it", () => {
    addRecent(1, "Photosynthesis");
    addRecent(2, "Bastille");
    addRecent(1, "Photosynthesis");
    const recents = getState().recents;
    expect(recents.map((r) => r.id)).toEqual([1, 2]);
  });

  it("keeps the list to six, dropping the oldest", () => {
    for (let i = 1; i <= 8; i++) addRecent(i, `M${i}`);
    const recents = getState().recents;
    expect(recents).toHaveLength(6);
    expect(recents.map((r) => r.id)).toEqual([8, 7, 6, 5, 4, 3]);
  });
});

describe("nudgeAllowed", () => {
  afterEach(() => vi.useRealTimers());

  it("stays suppressed for six hours after a dismissal, then returns", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-06T08:00:00Z"));
    dismissNudge();
    expect(nudgeAllowed()).toBe(false);

    // Exactly six hours is still suppressed — the check is strictly greater.
    vi.setSystemTime(new Date("2026-08-06T14:00:00Z"));
    expect(nudgeAllowed()).toBe(false);

    vi.setSystemTime(new Date("2026-08-06T14:00:01Z"));
    expect(nudgeAllowed()).toBe(true);
  });

  it("allows the first nudge before anything has been dismissed", () => {
    expect(nudgeAllowed()).toBe(true);
  });
});

describe("currentHour", () => {
  afterEach(() => vi.useRealTimers());

  // Bucket edges, in local time — an off-by-one here mislabels every session
  // logged at a boundary hour and quietly biases the time-of-day analysis.
  const cases: Array<[number, string]> = [
    [0, "night"],
    [4, "night"],
    [5, "morning"],
    [11, "morning"],
    [12, "afternoon"],
    [16, "afternoon"],
    [17, "evening"],
    [20, "evening"],
    [21, "night"],
    [23, "night"],
  ];

  it.each(cases)("hour %i is %s", (hour, expected) => {
    vi.useFakeTimers();
    const d = new Date(2026, 7, 6, hour, 30, 0); // local, not UTC
    vi.setSystemTime(d);
    expect(currentHour()).toBe(expected);
  });
});

describe("clearState", () => {
  it("removes the identity entirely", () => {
    setState({ userId: 4, recoveryKey: "tok" });
    clearState();
    expect(currentUserId()).toBeNull();
    expect(getState().recoveryKey).toBeNull();
  });
});
