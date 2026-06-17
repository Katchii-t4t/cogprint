import type {
  User,
  StudyGroup,
  StudyTechnique,
  TimeOfDay,
  MaterialAnalysisResponse,
  StudyPlanResponse,
  FingerprintResponse,
  PendingCheckItem,
  QuestionsResponse,
  StudySession,
  RetentionCheck,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  createUser: (group: StudyGroup) =>
    req<User>("/users", { method: "POST", body: JSON.stringify({ group }) }),

  analyzeMaterial: (title: string, raw_text: string) =>
    req<MaterialAnalysisResponse>("/materials/analyze", {
      method: "POST",
      body: JSON.stringify({ title, raw_text }),
    }),

  getQuestions: (materialId: number, n = 8) =>
    req<QuestionsResponse>(`/materials/${materialId}/questions?n=${n}`),

  flagQuestion: (materialId: number, cardId: number) =>
    req<{ material_id: number; card_id: number; flagged_count: number }>(
      `/materials/${materialId}/questions/flag`,
      { method: "POST", body: JSON.stringify({ card_id: cardId }) }
    ),

  getStudyPlan: (userId: number, materialId?: number, totalDays = 14) => {
    const params = new URLSearchParams({ total_days: String(totalDays) });
    if (materialId) params.set("material_id", String(materialId));
    return req<StudyPlanResponse>(`/users/${userId}/study-plan?${params}`);
  },

  logSession: (payload: {
    user_id: number;
    material_id?: number;
    technique: StudyTechnique;
    duration_minutes: number;
    time_of_day: TimeOfDay;
    quiz_score: number;
    sleep_hours?: number;
    stress_level?: number;
  }) =>
    req<StudySession>("/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  logRetentionCheck: (payload: {
    session_id: number;
    user_id: number;
    check_type: "24h" | "7d";
    score: number;
  }) =>
    req<RetentionCheck>("/retention-checks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getFingerprint: (userId: number) =>
    req<FingerprintResponse>(`/users/${userId}/fingerprint`),

  getPendingChecks: (userId: number) =>
    req<PendingCheckItem[]>(`/users/${userId}/pending-checks`),
};
