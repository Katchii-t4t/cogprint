"""
Monte Carlo studies of the recommendation loop.

These answer a different question from `predictive_baseline.py`. That one asks
whether personalisation *predicts* better. These ask whether the system, run
as a closed loop over months of simulated study, actually *acts* well — and
what happens when the world does not obey the model's assumptions.

What Monte Carlo can settle here: whether the algorithm is correct and
well-behaved given its assumptions, and how badly it degrades when they break.
What it cannot settle: whether the assumptions hold for real learners. It
assumes a between-person spread and asks "if the world were like this, would
the system find it and act on it". That is risk removed from the code, not
from the thesis. Only users remove the latter.

Study 1 — the closed loop (`--loop`)
------------------------------------
The recommender's output determines which technique gets used, which
determines what data is collected, which determines the next recommendation.
Nothing outside that loop corrects it. If it settles early on the wrong
technique it may never gather the evidence that would change its mind.

Four policies over identical simulated learners:

  ORACLE    always the technique that is genuinely best for this learner
  DUNLOSKY  always the highest research prior; never learns, never wrong-foots
  PLANNER   production `_technique_for_concept`, fed the data it has collected
  EXPLORER  PLANNER, but 20% of sessions pick a technique at random

EXPLORER is the control that prices exploration. If it beats PLANNER, the loop
is self-confirming and the fix is to assign some sessions rather than always
recommending.

Study 2 — misspecification (`--misspecified`)
---------------------------------------------
Every simulation elsewhere in this repo generates data under the model's own
exponential forgetting curve, which makes the model look better than any model
deserves. Wixted & Ebbesen (1991) argue forgetting follows a power law, not an
exponential. So generate R(t) = (1+t)^-b and fit the exponential anyway.

The question is not whether the numbers come out biased — they will. It is
whether the *ordering* of techniques survives, because the ordering is what
the recommendation actually uses. A biased estimate that ranks correctly still
gives correct advice.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field

import numpy as np

from agents.study_planner import _technique_for_concept
from personalization.hierarchical_memory import HierarchicalMemoryModel
from personalization.priors import prior_effectiveness, prior_stability_days

# All seven, matching RESEARCH_PRIORS. The planner can return any technique in
# a context's candidate list, so simulating a subset would crash on the first
# recommendation outside it — and, worse, would quietly exclude the two
# techniques whose reachability this whole line of work was about.
TECHNIQUES = (
    "practice_testing",
    "spaced_repetition",
    "active_recall",
    "elaborative_interrogation",
    "interleaving",
    "mind_maps",
    "re_reading",
)

# The material context the simulated learner is studying. Fixed on purpose: a
# varying context would let the plan look varied for reasons unrelated to what
# the loop learned.
CONTEXT = ("intermediate", "conceptual")

NOISE = 0.08  # matches _SIGMA_NOISE in hierarchical_memory


def _retention(t: float, S: float) -> float:
    return math.exp(-t / max(S, 1e-6))


# ── Study 1: the closed loop ──────────────────────────────────────────────────


@dataclass
class LoopResult:
    """Outcome of one policy over one simulated learner."""

    mean_retention: float          # true R(7) actually achieved, per session
    best_share: float              # fraction of sessions on the truly-best technique
    techniques_tried: int
    settled_on: str


@dataclass
class Learner:
    true_S: dict[str, float]

    @property
    def best(self) -> str:
        return max(self.true_S, key=lambda t: self.true_S[t])

    def study(self, technique: str, rng) -> tuple[float, float]:
        """One session: the 24h and 7d checks the app would record."""
        S = self.true_S[technique]
        return (
            float(np.clip(_retention(1.0, S) + rng.normal(0, NOISE), 0.01, 1.0)),
            float(np.clip(_retention(7.0, S) + rng.normal(0, NOISE), 0.01, 1.0)),
        )


def make_learner(rng, tau: float, sigma_person: float = 0.35) -> Learner:
    person = rng.normal(0.0, sigma_person)
    return Learner(
        {
            t: math.exp(math.log(prior_stability_days(t)) + person + rng.normal(0.0, tau))
            for t in TECHNIQUES
        }
    )


def run_loop(
    learner: Learner, policy: str, n_sessions: int, rng, epsilon: float = 0.2
) -> LoopResult:
    """Run one learner through `n_sessions`, choosing a technique each time.

    `observed` accrues only for techniques actually studied — that asymmetry
    is the whole point. A technique the policy stops choosing stops producing
    evidence, and its estimate freezes at whatever it was.
    """
    observed: dict[str, list[float]] = {t: [] for t in TECHNIQUES}
    used: list[str] = []
    achieved: list[float] = []

    for session in range(n_sessions):
        # eff_map exactly as production builds it: the mean measured 7-day
        # retention per technique, and nothing at all for the untried.
        eff_map = {t: float(np.mean(v)) for t, v in observed.items() if v}

        if policy == "ORACLE":
            technique = learner.best
        elif policy == "DUNLOSKY":
            technique = max(TECHNIQUES, key=prior_effectiveness)
        else:
            best_overall = (
                max(eff_map, key=lambda t: eff_map[t])
                if eff_map
                else max(TECHNIQUES, key=prior_effectiveness)
            )
            technique = _technique_for_concept(
                CONTEXT[0], CONTEXT[1], best_overall, eff_map, session
            )
            if policy == "EXPLORER" and rng.random() < epsilon:
                technique = TECHNIQUES[rng.integers(len(TECHNIQUES))]

        _, r7 = learner.study(technique, rng)
        observed[technique].append(r7)
        used.append(technique)
        # Scored on the truth, not the noisy observation: we are measuring what
        # the learner actually retained, not what the app happened to record.
        achieved.append(_retention(7.0, learner.true_S[technique]))

    tail = used[len(used) // 2:]  # the second half — where it has settled
    return LoopResult(
        mean_retention=float(np.mean(achieved)),
        best_share=float(np.mean([t == learner.best for t in tail])),
        techniques_tried=sum(1 for v in observed.values() if v),
        settled_on=max(set(tail), key=tail.count),
    )


def study_closed_loop(
    n_learners: int, n_sessions: int, tau: float, seed: int = 0
) -> dict[str, dict[str, float]]:
    rng = np.random.default_rng(seed)
    policies = ("ORACLE", "DUNLOSKY", "PLANNER", "EXPLORER")
    acc: dict[str, list[LoopResult]] = {p: [] for p in policies}

    for _ in range(n_learners):
        learner = make_learner(rng, tau)
        for policy in policies:
            # Same learner, same policy-independent draw order per policy: each
            # policy gets its own stream so one policy's extra random draws
            # cannot shift another's noise.
            acc[policy].append(
                run_loop(learner, policy, n_sessions, np.random.default_rng(rng.integers(2**31)))
            )

    return {
        p: {
            "retention": float(np.mean([r.mean_retention for r in rs])),
            "best_share": float(np.mean([r.best_share for r in rs])),
            "tried": float(np.mean([r.techniques_tried for r in rs])),
        }
        for p, rs in acc.items()
    }


# ── Study 2: misspecification ─────────────────────────────────────────────────


def _power_law_b(target_r7: float) -> float:
    """Power-law exponent giving R(7) = target, so the two worlds are
    comparable at the horizon the product actually reports."""
    return -math.log(target_r7) / math.log(8.0)


@dataclass
class MisspecResult:
    coverage: float = 0.0
    rank_agreement: float = 0.0
    picked_best: float = 0.0
    median_bias: float = 0.0
    samples: list[float] = field(default_factory=list)


def study_misspecified(
    n_learners: int, sessions_per_technique: int, tau: float, seed: int = 0,
    power_law: bool = True,
) -> MisspecResult:
    """Generate under a power law, fit with the exponential, and see what
    survives: the numbers, the ordering, or the decision."""
    rng = np.random.default_rng(seed)
    covered = 0
    total = 0
    rank_hits: list[float] = []
    picked_best: list[float] = []
    biases: list[float] = []

    for _ in range(n_learners):
        person = rng.normal(0.0, 0.35)
        true_r7: dict[str, float] = {}
        est_r7: dict[str, float] = {}

        for technique in TECHNIQUES:
            S_true = math.exp(
                math.log(prior_stability_days(technique)) + person + rng.normal(0.0, tau)
            )
            r7_true = _retention(7.0, S_true)
            true_r7[technique] = r7_true

            obs = []
            for _ in range(sessions_per_technique):
                for t in (1.0, 7.0):
                    if power_law:
                        r = (1.0 + t) ** (-_power_law_b(r7_true))
                    else:
                        r = _retention(t, S_true)
                    obs.append((t, float(np.clip(r + rng.normal(0, NOISE), 0.01, 1.0))))

            summary = HierarchicalMemoryModel().fit_user(obs)
            est_r7[technique] = _retention(7.0, summary.median)

            # Coverage is checked on R(7) rather than S: under a power law
            # there is no true S to cover, but R(7) is well defined in both
            # worlds and is what the product actually shows.
            lo = _retention(7.0, summary.ci_lower)
            hi = _retention(7.0, summary.ci_upper)
            covered += int(min(lo, hi) <= r7_true <= max(lo, hi))
            total += 1
            biases.append(est_r7[technique] - r7_true)

        true_order = sorted(TECHNIQUES, key=lambda t: true_r7[t], reverse=True)
        est_order = sorted(TECHNIQUES, key=lambda t: est_r7[t], reverse=True)
        rank_hits.append(_spearman(true_order, est_order))
        picked_best.append(float(est_order[0] == true_order[0]))

    return MisspecResult(
        coverage=covered / max(total, 1),
        rank_agreement=float(np.mean(rank_hits)),
        picked_best=float(np.mean(picked_best)),
        median_bias=float(np.median(biases)),
    )


def _spearman(order_a: list[str], order_b: list[str]) -> float:
    """Rank correlation between two orderings of the same items."""
    rank_a = {t: i for i, t in enumerate(order_a)}
    rank_b = {t: i for i, t in enumerate(order_b)}
    a = np.array([rank_a[t] for t in order_a], dtype=float)
    b = np.array([rank_b[t] for t in order_a], dtype=float)
    if np.std(a) == 0 or np.std(b) == 0:
        return 1.0
    return float(np.corrcoef(a, b)[0, 1])


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--loop", action="store_true", help="study 1: the closed loop")
    ap.add_argument("--misspecified", action="store_true", help="study 2: wrong curve")
    ap.add_argument("--learners", type=int, default=200)
    ap.add_argument("--sessions", type=int, default=60)
    args = ap.parse_args()

    if args.loop:
        print("\nStudy 1 — the closed loop\n")
        print("Mean true 7-day retention achieved per session, and the share of")
        print("later sessions spent on the technique genuinely best for that")
        print("learner. ORACLE is the ceiling; DUNLOSKY never learns.\n")
        for tau in (0.0, 0.3, 0.6):
            print(f"  tau={tau:.1f}  ({args.learners} learners x {args.sessions} sessions)")
            results = study_closed_loop(args.learners, args.sessions, tau, seed=1)
            print(f"    {'policy':<10}{'retention':>11}{'on best':>10}{'tried':>8}")
            for policy, r in results.items():
                print(
                    f"    {policy:<10}{r['retention']:>11.3f}"
                    f"{r['best_share']:>10.0%}{r['tried']:>8.1f}"
                )
            print()
        return

    if args.misspecified:
        print("\nStudy 2 — forgetting that does not obey the model\n")
        print("Data generated as R(t) = (1+t)^-b (power law), fitted with the")
        print("exponential the app uses. Matched at t=7 so the two worlds are")
        print("comparable where the product reports.\n")
        print(f"  {'world':<14}{'CI coverage':>13}{'rank agree':>12}{'picks best':>12}{'bias':>9}")
        for label, power in (("exponential", False), ("power law", True)):
            r = study_misspecified(60, 6, tau=0.4, seed=2, power_law=power)
            print(
                f"  {label:<14}{r.coverage:>13.0%}{r.rank_agreement:>12.2f}"
                f"{r.picked_best:>12.0%}{r.median_bias:>+9.3f}"
            )
        print("\n  'exponential' is the control: the model fitting its own world.")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
