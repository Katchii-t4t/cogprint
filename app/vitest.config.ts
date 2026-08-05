import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/**
 * Deliberately separate from vite.config.ts.
 *
 * The PWA plugin has no role in a jsdom run — it would generate a service
 * worker on every invocation and inject a `virtual:pwa-register` module that
 * tests then have to stub. Keeping the test config to just the React plugin
 * means a test failure is always about the code under test.
 *
 * Limitation worth stating: because this file duplicates nothing from
 * vite.config.ts, a future alias or `define` added there will NOT apply here.
 * If aliases appear, switch to `mergeConfig(viteConfig, ...)`.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // Pinned on purpose. The streak is computed in *local* calendar days, so
    // its edge cases are timezone-dependent: run under UTC (which is what CI
    // would otherwise give us) and the daylight-saving cases can never fail,
    // because UTC has none. Europe/Oslo is both DST-observing and where the
    // first beta cohort actually is. `src/streak.test.ts` asserts this took
    // effect, so a silent regression in the plumbing fails loudly.
    env: { TZ: "Europe/Oslo" },
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // Every test starts from a clean spy/mock slate; several of these suites
    // mock the whole api module, and leakage between them would be silent.
    restoreMocks: true,
    clearMocks: true,
  },
});
