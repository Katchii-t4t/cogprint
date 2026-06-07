import type {
  FingerprintResponse,
  MaterialAnalysisResponse,
  PendingCheckItem,
  RetentionCheck,
  StudyPlanResponse,
  StudySession,
  User,
} from "./types";

// Default "/api" uses the Vite dev proxy (see vite.config.ts). For a deploy,
// set VITE_API_BASE to the backend's absolute URL at build time.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

// Users
export const createUser = (group: "control" | "treatment", preTestScore?: number) =>
  req<User>("/users", {
    method: "POST",
    body: JSON.stringify({ group, pre_test_score: preTestScore ?? null }),
  });

export const getUser = (userId: number) =>
  req<User>(`/users/${userId}`);

export const updatePostTest = (userId: number, score: number) =>
  req<User>(`/users/${userId}/post-test`, {
    method: "PATCH",
    body: JSON.stringify({ post_test_score: score }),
  });

// Sessions
export const logSession = (body: {
  user_id: number;
  material_id?: number;
  technique: string;
  duration_minutes: number;
  time_of_day: string;
  sleep_hours?: number;
  stress_level?: number;
  quiz_score: number;
}) =>
  req<StudySession>("/sessions", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const listSessions = (userId: number) =>
  req<StudySession[]>(`/users/${userId}/sessions`);

// Retention checks
export const logRetentionCheck = (body: {
  session_id: number;
  user_id: number;
  check_type: "24h" | "7d";
  score: number;
}) =>
  req<RetentionCheck>("/retention-checks", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getPendingChecks = (userId: number) =>
  req<PendingCheckItem[]>(`/users/${userId}/pending-checks`);

// Fingerprint
export const getFingerprint = (userId: number) =>
  req<FingerprintResponse>(`/users/${userId}/fingerprint`);

export const rebuildFingerprint = (userId: number) =>
  req<FingerprintResponse>(`/users/${userId}/fingerprint/rebuild`, { method: "POST" });

// Materials
export const analyzeMaterial = (title: string, rawText: string) =>
  req<MaterialAnalysisResponse>("/materials/analyze", {
    method: "POST",
    body: JSON.stringify({ title, raw_text: rawText }),
  });

// Study plan
export const generateStudyPlan = (userId: number, materialId: number, totalDays = 14) =>
  req<StudyPlanResponse>(
    `/users/${userId}/study-plan?material_id=${materialId}&total_days=${totalDays}`
  );

// Research export — returns a CSV download
export const exportCSV = (group?: "control" | "treatment") => {
  const url = `${BASE}/export/study-data${group ? `?group=${group}` : ""}`;
  window.open(url, "_blank");
};
