import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Fingerprint from "./pages/Fingerprint";
import LogSession from "./pages/LogSession";
import Onboarding from "./pages/Onboarding";
import Researcher from "./pages/Researcher";
import RetentionCheck from "./pages/RetentionCheck";
import StudyPlan from "./pages/StudyPlan";

function RequireUser({ children }: { children: React.ReactNode }) {
  const userId = localStorage.getItem("cogprint_user_id");
  return userId ? <>{children}</> : <Navigate to="/onboarding" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/researcher" element={<Researcher />} />
        <Route
          path="/dashboard"
          element={
            <RequireUser>
              <Dashboard />
            </RequireUser>
          }
        />
        <Route
          path="/log-session"
          element={
            <RequireUser>
              <LogSession />
            </RequireUser>
          }
        />
        <Route
          path="/retention-check"
          element={
            <RequireUser>
              <RetentionCheck />
            </RequireUser>
          }
        />
        <Route
          path="/fingerprint"
          element={
            <RequireUser>
              <Fingerprint />
            </RequireUser>
          }
        />
        <Route
          path="/study-plan"
          element={
            <RequireUser>
              <StudyPlan />
            </RequireUser>
          }
        />
        <Route path="*" element={<Navigate to="/onboarding" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
