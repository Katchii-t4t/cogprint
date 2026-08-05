import { currentUserId } from "./store";

/**
 * Client-side funnel tracking (§2.1).
 *
 * Fire-and-forget by design: analytics is the least important thing happening
 * on any screen that calls it, so a failure here must be invisible to the user
 * and must never delay a render or a navigation.
 *
 * Keep properties non-identifying — ids, techniques and buckets, never the
 * text someone pasted. The events exist to answer "do people come back", not
 * to reconstruct what they studied.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export function track(eventName: string, properties?: Record<string, unknown>): void {
  try {
    void fetch(`${BASE}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_name: eventName,
        user_id: currentUserId(),
        properties: properties ?? null,
      }),
      // Survives the page navigation that often follows the event we're
      // recording (e.g. "round finished" immediately precedes a redirect).
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Never let telemetry surface to the user.
  }
}
