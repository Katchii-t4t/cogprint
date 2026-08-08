import { Component, type ErrorInfo, type ReactNode } from "react";
import { getState } from "../store";
import { track } from "../track";

/**
 * The last line of defence between a render error and a blank screen.
 *
 * This matters more here than in most apps. Identity lives in localStorage and
 * there is no account to log back into, so a white screen does not read as
 * "the app is broken" — it reads as "my study history is gone". Someone who
 * believes that has no reason to come back, and no way to tell they still
 * have their data.
 *
 * So the fallback does three things in order of importance: says the data is
 * safe, shows the recovery key if one exists (this is the only screen a
 * panicking user will reach), and offers a reload before a reset.
 *
 * Deliberately a class component — error boundaries have no hooks equivalent.
 */

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Fire-and-forget, and never allowed to throw: an exception in the error
    // handler replaces a recoverable screen with a genuinely blank one.
    try {
      track("render_error", {
        message: String(error?.message ?? "").slice(0, 200),
        component: String(info?.componentStack ?? "").slice(0, 300),
      });
    } catch {
      /* nothing useful left to do */
    }
  }

  render() {
    if (!this.state.error) return this.props.children;

    // Read at render rather than in state: if storage itself is what failed,
    // this must not be the thing that throws again.
    let recoveryKey: string | null = null;
    try {
      recoveryKey = getState().recoveryKey;
    } catch {
      recoveryKey = null;
    }

    return (
      <div className="min-h-dvh bg-ink-900 flex items-center justify-center px-4">
        <div className="w-full max-w-md rounded-3xl bg-ink-700 neural-border p-6 space-y-5 animate-fade-up">
          <div className="flex items-center gap-3">
            <span className="text-3xl" aria-hidden="true">🌿</span>
            <div>
              <h1 className="text-white font-bold text-lg">This screen broke</h1>
              <p className="text-slate-400 text-sm mt-0.5">
                Your study history is safe — nothing was lost.
              </p>
            </div>
          </div>

          {recoveryKey && (
            <div className="rounded-2xl bg-ink-800 border border-ink-500/40 p-4">
              <p className="text-slate-400 text-xs mb-2">
                Your recovery key, so you can get back in from anywhere:
              </p>
              <code className="text-neural text-xs break-all select-all">
                {recoveryKey}
              </code>
            </div>
          )}

          <div className="flex flex-col gap-2">
            <button
              onClick={() => window.location.reload()}
              className="w-full py-3 rounded-2xl bg-neural text-ink-900 font-semibold
                         active:scale-[0.98] transition-all focus-visible:outline-none
                         focus-visible:ring-2 focus-visible:ring-neural/60"
            >
              Reload
            </button>
            <button
              onClick={() => {
                window.location.href = "/";
              }}
              className="w-full py-3 rounded-2xl bg-ink-600 text-slate-300 font-medium
                         active:scale-[0.98] transition-all focus-visible:outline-none
                         focus-visible:ring-2 focus-visible:ring-neural/40"
            >
              Back to start
            </button>
          </div>

          <p className="text-slate-600 text-[11px] leading-relaxed">
            {/* Naming the error helps the one user who reports it, and costs
                nothing to the rest. Truncated so a long stack cannot dominate
                the screen. */}
            {String(this.state.error.message).slice(0, 160)}
          </p>
        </div>
      </div>
    );
  }
}
