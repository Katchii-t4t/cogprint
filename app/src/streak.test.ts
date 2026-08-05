import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getStreak, recordActivity } from "./streak";

const KEY = "cogprint_streak_v1";

/**
 * The streak is a motivator, not research data — but it is the most visible
 * number in the app, so getting it wrong is a trust problem. Every test here is
 * a way the count can be wrong while looking plausible.
 */

/** Write days directly, bypassing the clock, so a scenario reads as a table. */
function seedDays(days: Record<string, number>) {
  localStorage.setItem(KEY, JSON.stringify({ days }));
}

/** Local-midday, so a test never sits on a boundary by accident. */
function atLocalNoon(y: number, m: number, d: number) {
  vi.setSystemTime(new Date(y, m - 1, d, 12, 0, 0));
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it("runs under the pinned timezone the DST cases depend on", () => {
  // If this fails, the daylight-saving tests below became vacuous rather than
  // wrong — they would pass under UTC no matter what the code does.
  expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe("Europe/Oslo");
});

describe("qualifying score", () => {
  it("counts a day at exactly the 70% threshold", () => {
    atLocalNoon(2026, 8, 6);
    recordActivity(0.7);
    expect(getStreak().keptToday).toBe(true);
    expect(getStreak().current).toBe(1);
  });

  it("does not count a day just under the threshold", () => {
    atLocalNoon(2026, 8, 6);
    recordActivity(0.69);
    expect(getStreak().keptToday).toBe(false);
    expect(getStreak().current).toBe(0);
    // ...but the day still registers as studied. Showing up and doing badly is
    // not the same as not showing up, and the UI distinguishes the two.
    expect(getStreak().studiedToday).toBe(true);
  });

  it("keeps the best score of the day, so a bad second round can't undo a good first", () => {
    atLocalNoon(2026, 8, 6);
    recordActivity(0.9);
    recordActivity(0.2);
    expect(getStreak().keptToday).toBe(true);
  });
});

describe("current streak", () => {
  it("stays alive on a day that hasn't been studied yet", () => {
    // The day is not over. Zeroing the streak at midnight would punish someone
    // for opening the app in the morning.
    seedDays({ "2026-08-04": 0.8, "2026-08-05": 0.9 });
    atLocalNoon(2026, 8, 6);
    expect(getStreak().current).toBe(2);
    expect(getStreak().studiedToday).toBe(false);
  });

  it("breaks on a missed day", () => {
    seedDays({ "2026-08-01": 0.9, "2026-08-02": 0.9, "2026-08-04": 0.9 });
    atLocalNoon(2026, 8, 5);
    expect(getStreak().current).toBe(1); // only the 4th
  });

  it("is zero when the last qualifying day is two days back", () => {
    seedDays({ "2026-08-03": 0.9 });
    atLocalNoon(2026, 8, 6);
    expect(getStreak().current).toBe(0);
  });

  it("ignores days that were studied but not kept", () => {
    seedDays({ "2026-08-04": 0.9, "2026-08-05": 0.4 });
    atLocalNoon(2026, 8, 6);
    expect(getStreak().current).toBe(0);
  });
});

describe("local calendar days", () => {
  it("records late-evening activity against the local day, not the UTC one", () => {
    // 2026-08-06 23:30 in Oslo is 2026-08-06 21:30 UTC — same day either way.
    // 2026-08-06 00:30 Oslo is 2026-08-05 22:30 UTC, and that is the one that
    // would silently land on the wrong day under a UTC-based key.
    vi.setSystemTime(new Date(2026, 7, 6, 0, 30, 0));
    recordActivity(0.9);
    const stored = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    expect(Object.keys(stored.days)).toEqual(["2026-08-06"]);
  });

  it("counts a run across the spring daylight-saving change", () => {
    // Oslo springs forward on 2026-03-29: that calendar day is 23 hours long.
    // A "is b the next day after a?" test written as an exact 86,400,000 ms
    // difference silently returns false here and resets the longest streak.
    seedDays({
      "2026-03-28": 0.9,
      "2026-03-29": 0.9,
      "2026-03-30": 0.9,
    });
    atLocalNoon(2026, 3, 30);
    expect(getStreak().longest).toBe(3);
    expect(getStreak().current).toBe(3);
  });

  it("counts a run across the autumn daylight-saving change", () => {
    // 2026-10-25 in Oslo is 25 hours long — the mirror-image failure.
    seedDays({
      "2026-10-24": 0.9,
      "2026-10-25": 0.9,
      "2026-10-26": 0.9,
    });
    atLocalNoon(2026, 10, 26);
    expect(getStreak().longest).toBe(3);
    expect(getStreak().current).toBe(3);
  });
});

describe("longest streak", () => {
  it("reports the best historical run, not the current one", () => {
    seedDays({
      "2026-07-01": 0.9,
      "2026-07-02": 0.9,
      "2026-07-03": 0.9,
      "2026-07-04": 0.9,
      // gap
      "2026-08-05": 0.9,
    });
    atLocalNoon(2026, 8, 6);
    const s = getStreak();
    expect(s.longest).toBe(4);
    expect(s.current).toBe(1);
  });

  it("never lets the longest fall below the current", () => {
    seedDays({ "2026-08-04": 0.9, "2026-08-05": 0.9, "2026-08-06": 0.9 });
    atLocalNoon(2026, 8, 6);
    const s = getStreak();
    expect(s.longest).toBeGreaterThanOrEqual(s.current);
  });
});

describe("storage failures", () => {
  it("reads a corrupt store as empty rather than throwing", () => {
    localStorage.setItem(KEY, "{not json");
    atLocalNoon(2026, 8, 6);
    expect(() => getStreak()).not.toThrow();
    expect(getStreak().current).toBe(0);
  });

  it("swallows a write that storage rejects", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    atLocalNoon(2026, 8, 6);
    expect(() => recordActivity(0.9)).not.toThrow();
    spy.mockRestore();
  });
});
