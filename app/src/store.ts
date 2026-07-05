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
}

const EMPTY: AppState = {
  userId: null,
  group: null,
  lastMaterialId: null,
  lastMaterialTitle: null,
  lastMaterialText: null,
  recents: [],
  nudgeDismissedAt: null,
};

export function getState(): AppState {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : { ...EMPTY };
  } catch {
    return { ...EMPTY };
  }
}

export function setState(patch: Partial<AppState>) {
  const prev = getState();
  localStorage.setItem(KEY, JSON.stringify({ ...prev, ...patch }));
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

export function currentHour(): TimeOfDay {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  if (h < 21) return "evening";
  return "night";
}
