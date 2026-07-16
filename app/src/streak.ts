/**
 * #4 Retention streak — a streak that rewards *memory*, not app-opening.
 *
 * Purely local (localStorage). This is a motivator, not research data, so it
 * never touches the backend. A day "counts" when the user finishes a flashcard
 * round or a retention check with a qualifying score. Consecutive calendar days
 * with a qualifying activity make the streak.
 */

const KEY = "cogprint_streak_v1";
const QUALIFY_THRESHOLD = 0.7; // 70%+ counts as a "kept it" day

interface StreakStore {
  /** Map of YYYY-MM-DD (local) -> best score fraction that day. */
  days: Record<string, number>;
}

export interface StreakInfo {
  current: number;
  longest: number;
  studiedToday: boolean;
  keptToday: boolean; // hit the threshold today
}

function localDate(d = new Date()): string {
  // Local-timezone YYYY-MM-DD (avoids UTC off-by-one at day boundaries).
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function read(): StreakStore {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as StreakStore) : { days: {} };
  } catch {
    return { days: {} };
  }
}

function write(store: StreakStore) {
  try {
    localStorage.setItem(KEY, JSON.stringify(store));
  } catch {
    /* ignore quota errors — streak is best-effort */
  }
}

/** Call when a round/check finishes. `scoreFraction` is 0..1. */
export function recordActivity(scoreFraction: number) {
  const store = read();
  const today = localDate();
  const prev = store.days[today] ?? 0;
  store.days[today] = Math.max(prev, scoreFraction);
  write(store);
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return localDate(d);
}

export function getStreak(): StreakInfo {
  const store = read();
  const qualifies = (date: string) => (store.days[date] ?? -1) >= QUALIFY_THRESHOLD;

  // Current streak: walk backwards from today (today optional, so a streak
  // stays "alive" until the day actually ends without study).
  let current = 0;
  let offset = 0;
  if (!qualifies(daysAgo(0))) offset = 1; // today not done yet — start at yesterday
  while (qualifies(daysAgo(offset))) {
    current++;
    offset++;
  }

  // Longest streak over all recorded days.
  const sorted = Object.keys(store.days)
    .filter((d) => (store.days[d] ?? 0) >= QUALIFY_THRESHOLD)
    .sort();
  let longest = 0;
  let run = 0;
  let prevDate: string | null = null;
  for (const d of sorted) {
    if (prevDate && isNextDay(prevDate, d)) run++;
    else run = 1;
    longest = Math.max(longest, run);
    prevDate = d;
  }

  const today = localDate();
  return {
    current,
    longest,
    studiedToday: today in store.days,
    keptToday: (store.days[today] ?? 0) >= QUALIFY_THRESHOLD,
  };
}

function isNextDay(a: string, b: string): boolean {
  const da = new Date(a + "T00:00:00");
  const db = new Date(b + "T00:00:00");
  return db.getTime() - da.getTime() === 86_400_000;
}
