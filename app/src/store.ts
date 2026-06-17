import type { StudyGroup } from "./types";

const KEY = "cogprint_app_v1";

export interface AppState {
  userId: number | null;
  group: StudyGroup | null;
}

export function getState(): AppState {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : { userId: null, group: null };
  } catch {
    return { userId: null, group: null };
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

export function currentHour(): TimeOfDay {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  if (h < 21) return "evening";
  return "night";
}

type TimeOfDay = "morning" | "afternoon" | "evening" | "night";
