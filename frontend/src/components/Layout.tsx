import { Link, useLocation, useNavigate } from "react-router-dom";
import { getPendingChecks } from "../api";
import { useEffect, useState } from "react";

const NAV = [
  { to: "/dashboard",       label: "Dashboard" },
  { to: "/log-session",     label: "Log Session" },
  { to: "/fingerprint",     label: "My Fingerprint" },
  { to: "/study-plan",      label: "Study Plan" },
  { to: "/retention-check", label: "Retention Checks" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const name = localStorage.getItem("cogprint_name") ?? "Participant";
  const userId = Number(localStorage.getItem("cogprint_user_id"));
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    if (!userId) return;
    getPendingChecks(userId)
      .then((items) => setPendingCount(items.length))
      .catch(() => {});
  }, [userId, pathname]);

  function handleLogout() {
    localStorage.clear();
    navigate("/onboarding");
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top bar */}
      <header className="bg-brand-600 text-white shadow-md">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/dashboard" className="font-bold text-lg tracking-tight">
            🧠 CogPrint
          </Link>
          <div className="flex items-center gap-4 text-sm">
            <span className="opacity-75">ID #{userId} · {name}</span>
            <button
              onClick={handleLogout}
              className="opacity-75 hover:opacity-100 transition-opacity"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Nav */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 flex gap-1 overflow-x-auto">
          {NAV.map(({ to, label }) => {
            const isActive = pathname === to;
            const badge = to === "/retention-check" && pendingCount > 0;
            return (
              <Link
                key={to}
                to={to}
                className={`relative px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  isActive
                    ? "border-brand-600 text-brand-600"
                    : "border-transparent text-gray-600 hover:text-gray-900"
                }`}
              >
                {label}
                {badge && (
                  <span className="absolute top-2 right-1 h-4 w-4 rounded-full bg-red-500 text-white text-[10px] flex items-center justify-center">
                    {pendingCount}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Content */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-8">
        {children}
      </main>

      <footer className="text-center text-xs text-gray-400 py-4">
        CogPrint — Cognitive Fingerprint Project
      </footer>
    </div>
  );
}
