import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Grow from "./Grow";
import { setState } from "../store";
import { blindedFingerprint, fingerprintResponse, richFingerprint } from "../test/fixtures";
import type { StudyGroup } from "../types";

/**
 * Guardrail #2, at the layer that actually reaches a participant.
 *
 * insights.test.ts proves the sham *data* carries no measured signal. That is
 * not the same as proving the *screen* carries none: Grow reads some values
 * straight off the API response rather than off the view, and anything on that
 * path bypasses the sham entirely. These tests render the real component and
 * look at what a control user would see.
 */

vi.mock("../api", () => ({
  api: {
    getFingerprint: vi.fn(),
    getPendingChecks: vi.fn(),
    getBuddyForecast: vi.fn(),
    rebuildFingerprint: vi.fn(),
    getShareCode: vi.fn(),
    attachEmail: vi.fn(),
  },
}));

// Canvas is not implemented in jsdom, and the share card is not what these
// tests are about.
vi.mock("../lib/shareCard", () => ({
  renderShareCard: vi.fn(async () => new Blob()),
  shareFingerprint: vi.fn(async () => {}),
}));

vi.mock("../track", () => ({ track: vi.fn() }));

const { api } = await import("../api");

const USER_ID = 3;

/**
 * Renders Grow with the payload the *server actually sends that arm*. Control
 * gets the blinded profile, treatment gets the measured one. Feeding a control
 * render a measured payload would test a situation that cannot occur.
 */
async function renderGrow(group: StudyGroup | null) {
  setState({ userId: USER_ID, group });
  const fp = group === "control" ? blindedFingerprint(12) : richFingerprint();
  vi.mocked(api.getFingerprint).mockResolvedValue(fingerprintResponse(USER_ID, fp));
  vi.mocked(api.getPendingChecks).mockResolvedValue([]);

  render(
    <MemoryRouter initialEntries={["/grow"]}>
      <Grow />
    </MemoryRouter>
  );

  // The screen is loaded once the confidence pill is on it.
  await waitFor(() => expect(screen.getByText(/high confidence/i)).toBeInTheDocument());
}

beforeEach(() => {
  vi.mocked(api.getFingerprint).mockReset();
  vi.mocked(api.getPendingChecks).mockReset();
  // The study-buddy section fires its own request on mount and chains `.then`
  // on the result, so an unimplemented mock throws inside an effect rather
  // than failing an assertion. Give it a resolved default.
  vi.mocked(api.getShareCode).mockResolvedValue({
    user_id: USER_ID,
    share_code: "AB12CD",
  });
});

describe("a control participant's screen", () => {
  it("shows no memory forecast", async () => {
    await renderGrow("control");
    expect(screen.queryByText(/memory forecast/i)).not.toBeInTheDocument();
  });

  it("shows no learner archetype", async () => {
    await renderGrow("control");
    // The fixture types as a Specialist: high confidence, one clear best
    // technique out of three rated.
    expect(screen.queryByText(/climber|marathoner|sprinter|specialist|explorer/i))
      .not.toBeInTheDocument();
  });

  it("shows no Bayesian confidence band", async () => {
    // The leak this test exists for: the band is computed from
    // `technique_stability` on the raw API response, not from the sham view.
    // The backend returns that array for every user regardless of arm, so an
    // ungated band prints a real 95% interval next to a fabricated percentage
    // — both a blind break and a visibly self-contradictory card.
    await renderGrow("control");
    expect(screen.queryByText(/likely \d+–\d+%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/early estimate/i)).not.toBeInTheDocument();
  });

  it("does not carry any real insight text", async () => {
    await renderGrow("control");
    for (const real of richFingerprint().insights) {
      const claim = real.split("?")[0];
      expect(screen.queryByText(new RegExp(claim.slice(0, 24), "i"))).not.toBeInTheDocument();
    }
  });

  it("never renders the payload's own group label", async () => {
    // The blinded payload carries a data_gaps string that names the arm
    // outright. Nothing renders data_gaps today; this pins that it stays so.
    await renderGrow("control");
    expect(screen.queryByText(/personalisation not enabled/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/study group/i)).not.toBeInTheDocument();
  });

  it("is not visibly emptier than a treatment screen", async () => {
    // If control users can tell they are in the control arm, the comparison is
    // dead. Every section the treatment screen fills must be filled here too —
    // from the *blinded* payload, which is the only one control ever receives.
    await renderGrow("control");
    expect(screen.getByText(/technique effectiveness/i)).toBeInTheDocument();
    expect(screen.getByText(/memory stability per technique/i)).toBeInTheDocument();
    expect(screen.getByText(/what your data says/i)).toBeInTheDocument();
    expect(screen.getByText(/best technique for you/i)).toBeInTheDocument();
  });

  it("is not stranded on the growing state after weeks of study", async () => {
    // The regression this exists for. The screen's whole body is gated on
    // `confidence !== "low"`, and the backend pinned control to "low"
    // regardless of effort — so a control participant with 12 sessions saw
    // "your fingerprint is growing / processing your first insights" beside an
    // honest "12 sessions" counter, permanently, while treatment saw the full
    // screen. Noticing that takes no knowledge of the study design at all.
    await renderGrow("control");
    expect(screen.queryByText(/your fingerprint is growing/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/processing your first insights/i)).not.toBeInTheDocument();
  });

  it("still shows the growing state to a genuinely new control user", async () => {
    // The flip side: at session zero, "growing" is the honest screen for both
    // arms, and treatment shows it too.
    setState({ userId: USER_ID, group: "control" });
    vi.mocked(api.getFingerprint).mockResolvedValue(
      fingerprintResponse(USER_ID, blindedFingerprint(0, "low"))
    );
    vi.mocked(api.getPendingChecks).mockResolvedValue([]);
    render(
      <MemoryRouter initialEntries={["/grow"]}>
        <Grow />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByText(/your fingerprint is growing/i)).toBeInTheDocument()
    );
  });

  it("still reports the honest session count", async () => {
    // Growth is measured, not personalised. Faking it would corrupt the number
    // the analytics funnel reads.
    await renderGrow("control");
    expect(screen.getByText("12 sessions")).toBeInTheDocument();
  });
});

describe("a treatment participant's screen", () => {
  it("shows the memory forecast", async () => {
    await renderGrow("treatment");
    expect(screen.getByText(/memory forecast/i)).toBeInTheDocument();
  });

  it("shows the learner archetype", async () => {
    await renderGrow("treatment");
    expect(screen.getByText(/specialist/i)).toBeInTheDocument();
  });

  it("shows the confidence band, so the uncertainty is visible", async () => {
    // Guardrail #3 in the other direction: the treatment arm must see the
    // range, not a bare point estimate posing as a measurement.
    await renderGrow("treatment");
    expect(screen.getAllByText(/likely \d+–\d+%/).length).toBeGreaterThan(0);
  });

  it("shows the user's real insight text", async () => {
    await renderGrow("treatment");
    expect(screen.getByText(/which technique holds up after a week/i)).toBeInTheDocument();
  });
});

describe("an unassigned user", () => {
  it("is treated as treatment, matching the documented default", async () => {
    // Pinned rather than endorsed. `group` is null only before assignment, and
    // the personalised screen is the better default for a plain consumer user
    // — but if that ever changes, it should change deliberately, not by drift.
    await renderGrow(null);
    expect(screen.getByText(/memory forecast/i)).toBeInTheDocument();
  });
});

describe("failure states", () => {
  it("does not leave the user on a spinner when the fingerprint call fails", async () => {
    // A rejected promise that never clears `loading` is an infinite spinner —
    // the single worst outcome for a screen that is the app's whole payoff.
    setState({ userId: USER_ID, group: "treatment" });
    vi.mocked(api.getFingerprint).mockRejectedValue(new Error("500: boom"));
    vi.mocked(api.getPendingChecks).mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={["/grow"]}>
        <Grow />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(screen.getByText(/your fingerprint is growing/i)).toBeInTheDocument()
    );
  });

  it("offers a rebuild when the last background rebuild failed", async () => {
    setState({ userId: USER_ID, group: "treatment" });
    vi.mocked(api.getFingerprint).mockResolvedValue(
      fingerprintResponse(USER_ID, richFingerprint(), { rebuild_status: "failed" })
    );
    vi.mocked(api.getPendingChecks).mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={["/grow"]}>
        <Grow />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /rebuild/i })).toBeInTheDocument()
    );
    expect(screen.getByText(/this view may be stale/i)).toBeInTheDocument();
  });
});
