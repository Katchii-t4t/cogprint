import type { StudyGroup } from "./types";

const KEY = "cogprint_app_v1";

export type TimeOfDay = "morning" | "afternoon" | "evening" | "night";

export interface RecentMaterial {
  id: number;
  title: string;
  ts: number;
}

export interface AppState {
  userId: number | null;
  group: StudyGroup | null;
  /** Display name, client-side only (no account, no login wall). */
  name: string | null;
  /** Most recently analysed material — lets /plan and /grow recover it when
      it isn't in the URL (e.g. the user navigates back to the plan). */
  lastMaterialId: number | null;
  /** Title of the last material, for friendlier headings. */
  lastMaterialTitle: string | null;
  /** The raw pasted text, kept client-side so the Study screen can show it
      without a round trip — the backend has no GET /materials/{id}. */
  lastMaterialText: string | null;
  /** Recently analysed materials (newest first) — cached on the backend, so
      re-opening one is instant: no re-analysis, no re-generation. */
  recents: RecentMaterial[];
  /** When the forgetting-nudge was last dismissed (rate-limits it to ~6h). */
  nudgeDismissedAt: number | null;
  /** #9 study-buddy: a friend's share code we're following (their forecast). */
  buddyCode: string | null;
  /** Account-recovery token, issued once at sign-up. The only way back into
      this account from another device or after storage is cleared — the server
      keeps only a hash and cannot re-issue it. */
  recoveryKey: string | null;
}

/** A function, not a constant: a shared `{ ...EMPTY }` is a *shallow* copy, so
    every caller would receive the same `recents` array and one push anywhere
    would corrupt the default for the whole session. */
function empty(): AppState {
  return {
    userId: null,
    group: null,
    name: null,
    lastMaterialId: null,
    lastMaterialTitle: null,
    lastMaterialText: null,
    recents: [],
    nudgeDismissedAt: null,
    buddyCode: null,
    recoveryKey: null,
  };
}

export function getState(): AppState {
  try {
    const raw = localStorage.getItem(KEY);
    // Merging onto a fresh default is what lets a state written by an older
    // build — one with no `recents` key at all — still read as valid here.
    return raw ? { ...empty(), ...JSON.parse(raw) } : empty();
  } catch {
    return empty();
  }
}

export function setState(patch: Partial<AppState>) {
  const prev = getState();
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...prev, ...patch }));
  } catch {
    // Storage can refuse: iOS Safari in private mode throws from setItem, and
    // any browser throws at quota. Persistence is genuinely lost when that
    // happens and this session's identity will not survive a reload — but the
    // caller is usually the sign-up handler, and crashing it turns a degraded
    // session into a white screen. The worse outcome is the unhandled throw.
  }
}

export function clearState() {
  localStorage.removeItem(KEY);
}

export function currentUserId(): number | null {
  return getState().userId;
}

export function lastMaterialId(): number | null {
  return getState().lastMaterialId;
}

export function addRecent(id: number, title: string) {
  const prev = getState().recents.filter((r) => r.id !== id);
  setState({ recents: [{ id, title, ts: Date.now() }, ...prev].slice(0, 6) });
}

/** Gentle nudges only: show at most once per ~6 hours after a dismissal. */
export function nudgeAllowed(): boolean {
  const at = getState().nudgeDismissedAt;
  return !at || Date.now() - at > 6 * 60 * 60 * 1000;
}

export function dismissNudge() {
  setState({ nudgeDismissedAt: Date.now() });
}

/**
 * The client is the only place a session's time-of-day label is decided — the
 * backend stores whatever it is sent — so this bucketing *is* the definition
 * used by the optimal-conditions analysis.
 *
 * The small hours belong to night, not morning. A 2am session pooled with 9am
 * ones drags a night owl's `best_time_of_day` toward "morning", which is the
 * opposite of the advice they need. Sessions logged before this boundary
 * moved are not relabelled; with no production users yet that is a handful of
 * local rows, not a migration.
 */
export function currentHour(): TimeOfDay {
  const h = new Date().getHours();
  if (h < 5) return "night";
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  if (h < 21) return "evening";
  return "night";
}
