import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

/**
 * Test bootstrap.
 *
 * The app keeps identity in localStorage (`store.ts`) and a streak in a second
 * key (`streak.ts`), and both are module-level singletons from the test's point
 * of view. Without an explicit wipe between tests, a user id set by one test
 * leaks into the next and the failure shows up somewhere unrelated.
 */

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.useRealTimers();
});

// jsdom implements neither of these, and several screens call them on mount or
// on a user gesture. Stubbing them here rather than per-test keeps the failure
// mode honest: a test that fails is failing on logic, not on a missing browser
// API. `matchMedia` in particular backs the prefers-reduced-motion checks.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
