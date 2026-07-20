import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Paste from "./pages/Paste";

// Perf (§6): the paste screen is the app's front door and stays in the main
// bundle; every other route is lazy-loaded so first paint stays tiny.
const Plan = lazy(() => import("./pages/Plan"));
const Study = lazy(() => import("./pages/Study"));
const Cards = lazy(() => import("./pages/Cards"));
const Grow = lazy(() => import("./pages/Grow"));
const Checks = lazy(() => import("./pages/Checks"));
const Library = lazy(() => import("./pages/Library"));

/** Route-transition fallback — same spinner language as the in-page loaders. */
function RouteFallback() {
  return (
    <div className="flex-1 flex items-center justify-center min-h-dvh bg-ink-900">
      <div className="w-8 h-8 rounded-full border-2 border-neural/40 border-t-neural animate-spin" />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<Paste />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/study" element={<Study />} />
          <Route path="/cards" element={<Cards />} />
          <Route path="/grow" element={<Grow />} />
          <Route path="/checks" element={<Checks />} />
          <Route path="/library" element={<Library />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
