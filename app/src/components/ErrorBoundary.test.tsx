import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";
import { setState } from "../store";

vi.mock("../track", () => ({ track: vi.fn() }));

const { track } = await import("../track");

function Boom(): never {
  throw new Error("render exploded");
}

/**
 * A white screen means something different in this app than in most.
 *
 * There is no account to log back into — identity lives in localStorage — so a
 * blank page does not read as "the app is broken", it reads as "my study
 * history is gone". Someone who believes that has no reason to return and no
 * way to discover they still have their data.
 */

let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  // React logs the caught error itself; silencing keeps the test output honest
  // about what actually failed.
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => consoleError.mockRestore());

describe("when a screen throws", () => {
  it("shows a recovery screen instead of nothing", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText(/this screen broke/i)).toBeInTheDocument();
  });

  it("says the data is safe, because that is the user's actual fear", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText(/nothing was lost/i)).toBeInTheDocument();
  });

  it("surfaces the recovery key — this is the screen a panicking user reaches", () => {
    setState({ userId: 4, recoveryKey: "tok_abcdef123456" });
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText("tok_abcdef123456")).toBeInTheDocument();
  });

  it("offers a reload before a reset", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    const buttons = screen.getAllByRole("button").map((b) => b.textContent);
    expect(buttons[0]).toMatch(/reload/i);
    expect(buttons[1]).toMatch(/back to start/i);
  });

  it("reports the failure so it is not invisible", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(track).toHaveBeenCalledWith("render_error", expect.anything());
  });

  it("still renders the fallback when reporting throws", () => {
    // An exception inside the error handler would replace a recoverable screen
    // with a genuinely blank one — the exact outcome this component exists to
    // prevent.
    vi.mocked(track).mockImplementationOnce(() => {
      throw new Error("analytics is also down");
    });
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText(/this screen broke/i)).toBeInTheDocument();
  });

  it("still renders the fallback when storage itself is what failed", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("SecurityError");
    });
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText(/this screen broke/i)).toBeInTheDocument();
    spy.mockRestore();
  });
});

describe("when nothing throws", () => {
  it("renders its children untouched", () => {
    render(
      <ErrorBoundary>
        <p>the actual app</p>
      </ErrorBoundary>
    );
    expect(screen.getByText("the actual app")).toBeInTheDocument();
    expect(screen.queryByText(/this screen broke/i)).not.toBeInTheDocument();
  });
});
