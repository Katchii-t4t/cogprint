import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Cards from "./Cards";
import { setState } from "../store";
import type { Flashcard } from "../types";

/**
 * The study round is where the fingerprint gets its data, so a wrong value
 * logged here is worse than a crash: it silently trains the model on something
 * that did not happen. Every test below is a way that could occur.
 *
 * The rule these enforce, from study.ts: only ever log a technique the user
 * actually performed, and only ever score answers that were objectively
 * graded.
 */

vi.mock("../api", () => ({
  api: {
    getQuestions: vi.fn(),
    logSession: vi.fn(),
    flagQuestion: vi.fn(),
  },
}));

vi.mock("../track", () => ({ track: vi.fn() }));

const { api } = await import("../api");
const { track } = await import("../track");

const USER_ID = 5;
const MATERIAL_ID = 9;

function card(n: number, over: Partial<Flashcard> = {}): Flashcard {
  return {
    id: n,
    question: `Question ${n}`,
    answer: `Answer ${n}`,
    concept: `Concept ${n}`,
    difficulty: "intermediate",
    flagged: false,
    distractors: [`Wrong ${n}a`, `Wrong ${n}b`, `Wrong ${n}c`],
    ...over,
  };
}

/** Shows where the round ended up, so navigation is asserted through the real
    router rather than through a mocked useNavigate. */
function Landing() {
  const loc = useLocation();
  return <div data-testid="landing">{loc.pathname + loc.search}</div>;
}

function renderRound(cards: Flashcard[], search = "") {
  setState({ userId: USER_ID, group: "treatment", lastMaterialId: MATERIAL_ID });
  vi.mocked(api.getQuestions).mockResolvedValue({
    material_id: MATERIAL_ID,
    title: "Test material",
    cards,
    generated_by: "local:cloze",
  });

  return render(
    <MemoryRouter initialEntries={[`/cards${search}`]}>
      <Routes>
        <Route path="/cards" element={<Cards />} />
        <Route path="/grow" element={<Landing />} />
        <Route path="/" element={<Landing />} />
      </Routes>
    </MemoryRouter>
  );
}

/** Answer the card currently on screen, then let the feedback pause elapse. */
async function answerQuiz(option: string) {
  const button = await screen.findByRole("button", { name: option });
  act(() => button.click());
  // pick() waits 600ms on a hit and 1400ms on a miss before advancing.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1500);
  });
}

beforeEach(() => {
  // `shouldAdvanceTime` is required, not cosmetic: Testing Library's findBy*
  // and waitFor poll on real timers, so under plain fake timers every async
  // query hangs until the test times out. This keeps the clock moving while
  // still allowing the explicit jumps over the round's feedback pauses.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.getQuestions).mockReset();
  vi.mocked(api.logSession).mockReset().mockResolvedValue({} as never);
  vi.mocked(api.flagQuestion).mockReset().mockResolvedValue({} as never);
  vi.mocked(track).mockReset();
});

describe("the technique the round logs", () => {
  it("logs the technique the user picked, not a hardcoded default", async () => {
    renderRound([card(1)], "?mode=practice_testing");
    await answerQuiz("Answer 1");

    await waitFor(() => expect(api.logSession).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.logSession).mock.calls[0][0].technique).toBe("practice_testing");
  });

  it("logs elaborative interrogation when that is the chosen mode", async () => {
    renderRound([card(1)], "?mode=elaborative_interrogation");
    await answerQuiz("Answer 1");

    await waitFor(() => expect(api.logSession).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.logSession).mock.calls[0][0].technique).toBe(
      "elaborative_interrogation"
    );
  });

  it("refuses to log a technique the round did not actually deliver", async () => {
    // ?mode=spaced_repetition is reachable by hand. Spaced repetition is a
    // schedule, not a card round; logging it would tell the fingerprint the
    // user did something they did not, and that error is unrecoverable — it
    // looks like real evidence forever after.
    renderRound([card(1)], "?mode=spaced_repetition");
    await answerQuiz("Answer 1");

    await waitFor(() => expect(api.logSession).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.logSession).mock.calls[0][0].technique).toBe("active_recall");
  });

  it("reports the same technique to analytics as to the fingerprint", async () => {
    // Two sources of truth that can disagree would make the funnel data
    // uninterpretable next to the session data.
    renderRound([card(1)], "?mode=re_reading");
    await answerQuiz("Answer 1");

    await waitFor(() => expect(track).toHaveBeenCalledWith("round_completed", expect.anything()));
    const props = vi.mocked(track).mock.calls.find((c) => c[0] === "round_completed")?.[1];
    expect(props?.technique).toBe("re_reading");
    expect(vi.mocked(api.logSession).mock.calls[0][0].technique).toBe("re_reading");
  });
});

describe("what counts as measurement", () => {
  it("scores only the objectively graded answers", async () => {
    renderRound([card(1), card(2), card(3), card(4)]);
    await answerQuiz("Answer 1");
    await answerQuiz("Answer 2");
    await answerQuiz("Answer 3");
    await answerQuiz("Wrong 4a");

    await waitFor(() => expect(api.logSession).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.logSession).mock.calls[0][0].quiz_score).toBeCloseTo(0.75, 6);
    expect(await screen.findByTestId("landing")).toHaveTextContent("/grow?score=75");
  });

  it("never logs a session from a flashcard round", async () => {
    // Flashcards are self-reported. Feeding "I got it" into the fingerprint
    // would measure confidence, not memory.
    renderRound([card(1)]);
    const flashTab = await screen.findByRole("button", { name: /flashcards/i });
    act(() => flashTab.click());

    act(() => screen.getByText("Question 1").click()); // flip
    act(() => screen.getByRole("button", { name: /got it/i }).click());

    expect(await screen.findByTestId("landing")).toHaveTextContent("/grow?practice=1");
    expect(api.logSession).not.toHaveBeenCalled();
  });

  it("never logs a session when no card in the round was gradeable", async () => {
    // A cache written before distractors existed. These render as flashcards
    // inside a quiz round and must not produce a score of 100%.
    renderRound([card(1, { distractors: [] }), card(2, { distractors: [] })]);

    for (let i = 1; i <= 2; i++) {
      const question = await screen.findByText(`Question ${i}`);
      act(() => question.click()); // flip
      act(() => screen.getByRole("button", { name: /got it/i }).click());
    }

    expect(await screen.findByTestId("landing")).toHaveTextContent("/grow?practice=1");
    expect(api.logSession).not.toHaveBeenCalled();
  });

  it("excludes a flagged card from the score instead of marking it wrong", async () => {
    // Flagging says "this question is broken", which is not evidence about the
    // user. Counting it as a miss would punish them for the generator's fault.
    renderRound([card(1), card(2)]);

    const flag = await screen.findByRole("button", { name: /flag it/i });
    act(() => flag.click());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    await answerQuiz("Answer 2");

    await waitFor(() => expect(api.logSession).toHaveBeenCalledTimes(1));
    const call = vi.mocked(api.logSession).mock.calls[0][0];
    expect(call.quiz_score).toBe(1); // one gradeable card, answered correctly
    expect(await screen.findByTestId("landing")).toHaveTextContent("/grow?score=100");
  });

  it("hides flagged cards from the round entirely", async () => {
    renderRound([card(1, { flagged: true }), card(2)]);
    expect(await screen.findByText("Question 2")).toBeInTheDocument();
    expect(screen.queryByText("Question 1")).not.toBeInTheDocument();
  });
});

describe("the session payload", () => {
  it("never reports a zero-minute session", async () => {
    // A fast round would round to 0, and duration feeds the optimal-duration
    // correlation — a zero there is a data point that cannot be true.
    renderRound([card(1)]);
    await answerQuiz("Answer 1");

    await waitFor(() => expect(api.logSession).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.logSession).mock.calls[0][0].duration_minutes).toBeGreaterThanOrEqual(1);
  });

  it("attributes the session to the material that was studied", async () => {
    renderRound([card(1)], "?m=42");
    await answerQuiz("Answer 1");

    await waitFor(() => expect(api.logSession).toHaveBeenCalledTimes(1));
    const call = vi.mocked(api.logSession).mock.calls[0][0];
    expect(call.material_id).toBe(42);
    expect(call.user_id).toBe(USER_ID);
  });

  it("still shows the user their score when logging fails", async () => {
    // The fingerprint rebuild is best-effort; the round is not. Losing the
    // score screen over a network blip would read as "my work vanished".
    vi.mocked(api.logSession).mockRejectedValue(new Error("500: boom"));
    renderRound([card(1)]);
    await answerQuiz("Answer 1");

    expect(await screen.findByTestId("landing")).toHaveTextContent("/grow?score=100");
  });
});

describe("entry guards", () => {
  it("sends a user with no identity back to the front door", async () => {
    localStorage.clear();
    render(
      <MemoryRouter initialEntries={["/cards?m=1"]}>
        <Routes>
          <Route path="/cards" element={<Cards />} />
          <Route path="/" element={<Landing />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByTestId("landing")).toHaveTextContent("/");
  });
});
