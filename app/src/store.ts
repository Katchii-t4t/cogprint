import type { StudyGroup } from "./types";

const KEY = "cogprint_app_v1";

export type TimeOfDay = "morning" | "afternoon" | "evening" | "night";

export interface AppState {
  userId: number | null;
  group: StudyGroup | null;
  /** Most recently analysed material — lets /plan and /grow recover it when
      it isn't in the URL (e.g. the user navigates back to the plan). */
  lastMaterialId: number | null;
  /** Title of the last material, for friendlier headings. */
  lastMaterialTitle: string | null;
  /** #9 study-buddy: a friend's share code we're following (their forecast). */
  buddyCode: string | null;
}

const EMPTY: AppState = {
  userId: null,
  group: null,
  lastMaterialId: null,
  lastMaterialTitle: null,
  buddyCode: null,
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

export function currentHour(): TimeOfDay {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  if (h < 21) return "evening";
  return "night";
}
