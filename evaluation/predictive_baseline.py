"""
Does personalisation actually predict better than the research prior?

This is the offline answer to the one question that decides whether CogPrint's
core differentiator is worth anything. It needs no RCT, no control arm and no
extra participants — only the retention checks the app already collects.

The three predictors
--------------------
Each predicts R̂ for a held-out retention observation at delay t, via the
Ebbinghaus curve R(t) = exp(-t / S). They differ only in where S comes from:

  PRIOR     S = research prior for that technique (personalization/priors.py).
            No personalisation whatsoever. This is the "good generic advice"
            baseline — a Dunlosky lookup table.

  PERSON    S = prior[technique] × m_user, one multiplier fitted per person.
            "You forget more slowly than average, but which technique suits
            you is the population's answer." Personalises scheduling, not
            technique choice.

  PERSONAL  S = one posterior per (person, technique). This is the product's
            actual claim: that which technique works varies by individual.

Why PERSON is the baseline that matters
---------------------------------------
PERSONAL vs PRIOR alone cannot distinguish "this person forgets slowly" from
"this person forgets slowly *when using this technique*". Only the first is
needed to schedule reviews well; the second is what justifies per-person
technique recommendations, the moat, and the whole personalisation thesis.

The first version of this file used a "one S per person, pooled across
techniques" baseline instead, and it was wrong in a way worth recording: that
model cannot represent the fact that techniques differ *at the population
level* either, so it loses to PERSONAL even when no per-person variation
exists at all. On simulated data with the interaction set to exactly zero it
declared personalisation a 100% winner. A baseline has to be beatable only by
the effect you are actually claiming.

  PERSONAL beats PERSON   → between-person variation in technique effect is
                            real, and personalised technique choice has value.
  PERSONAL ≈ PERSON       → people differ in memory strength but not in which
                            technique suits them. Personalised *scheduling* is
                            still worth having; personalised *technique* is not.
  PERSON ≈ PRIOR          → the individual data is not even improving the
                            forgetting-rate estimate yet. Usually means too few
                            observations, not that the model is wrong.

What this cannot tell you
-------------------------
Technique is self-selected: a learner picks re-reading for material they
already half-know. So a PERSONAL win is evidence of a real *predictive*
association, not of a causal technique effect. Separating those needs the app
to sometimes assign the technique rather than offer it. Stated plainly here
because the number this script prints is easy to over-read.

Usage
-----
    python -m evaluation.predictive_baseline --db          # real users
    python -m evaluation.predictive_baseline --simulate    # power study
"""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from personalization.hierarchical_memory import HierarchicalMemoryModel, PopulationParams
from personalization.priors import prior_stability_days

# A held-out observation: how long after the session, and what was recalled.
Observation = tuple[float, float]  # (t_days, R_observed)

# Minimum observations a (user, technique) cell needs before it can contribute
# a held-out point. Below this there is nothing to fit on after the split, and
# including such cells measures the split, not the model.
MIN_TRAIN_OBS = 2
MIN_HELDOUT_OBS = 1


@dataclass
class Cell:
    """One (user, technique) pair's observations, in chronological order."""

    user_id: int
    technique: str
    observations: list[Observation] = field(default_factory=list)


@dataclass
class Scores:
    """Prediction errors for one predictor, one error per held-out point."""

    name: str
    errors: list[float] = field(default_factory=list)

    @property
    def mae(self) -> float:
        return float(np.mean(np.abs(self.errors))) if self.errors else float("nan")

    @property
    def rmse(self) -> float:
        return float(np.sqrt(np.mean(np.square(self.errors)))) if self.errors else float("nan")

    @property
    def n(self) -> int:
        return len(self.errors)


def _retention(t: float, S: float) -> float:
    """Ebbinghaus R(t) = exp(-t/S), clamped away from a degenerate S."""
    return math.exp(-t / max(S, 1e-6))


def _fit_S(model: HierarchicalMemoryModel, obs: list[Observation]) -> float:
    """Posterior median stability for a set of observations.

    Median rather than mean: the posterior over S is right-skewed in log space,
    and a single lucky high-retention check can drag the mean a long way.
    """
    return model.fit_user(obs).median


# ── Splitting ─────────────────────────────────────────────────────────────────


def prospective_split(
    cell: Cell, holdout_fraction: float = 0.3
) -> tuple[list[Observation], list[Observation]]:
    """Split a cell's observations into (train, heldout) by time order.

    Prospective on purpose. A random split leaks: two checks from the *same*
    study session (24h and 7d) share a single latent S and a single material,
    so putting one in train and the other in test lets the model half-see its
    own answer, and every predictor looks better than it is — the personalised
    one most of all, because it has the most parameters to overfit with.
    """
    n_holdout = max(MIN_HELDOUT_OBS, int(round(len(cell.observations) * holdout_fraction)))
    if len(cell.observations) - n_holdout < MIN_TRAIN_OBS:
        return [], []
    cut = len(cell.observations) - n_holdout
    return cell.observations[:cut], cell.observations[cut:]


# ── Evaluation ────────────────────────────────────────────────────────────────


def evaluate(
    cells: list[Cell],
    holdout_fraction: float = 0.3,
    population: PopulationParams | None = None,
) -> dict[str, Scores]:
    """Score all three predictors on the same held-out points.

    Every predictor is scored on an identical set of observations — a cell that
    cannot be split contributes to none of them. Comparing predictors that saw
    different test sets is the easiest way to produce a meaningless win.
    """
    prior_s = Scores("PRIOR")
    person_s = Scores("PERSON")
    personal_s = Scores("PERSONAL")

    # Group cells by user so the person-level fit sees everything they did.
    by_user: dict[int, list[Cell]] = defaultdict(list)
    for c in cells:
        by_user[c.user_id].append(c)

    for user_cells in by_user.values():
        splits = {c.technique: prospective_split(c, holdout_fraction) for c in user_cells}
        usable = {t: (tr, ho) for t, (tr, ho) in splits.items() if tr and ho}
        if not usable:
            continue

        model = HierarchicalMemoryModel(population)

        # PERSON: fit a single multiplier m on the prior stabilities.
        #
        # R = exp(-t / (m · S_prior[k])) = exp(-(t / S_prior[k]) / m), so
        # rescaling each observation's delay by that technique's prior turns
        # the multiplier into an ordinary stability fit — the same production
        # sampler, no second implementation to keep honest. The prior on m is
        # centred at 1 (log 0), i.e. "this person is average until shown
        # otherwise".
        rescaled: list[Observation] = []
        for technique, (train, _) in usable.items():
            s_prior = prior_stability_days(technique)
            rescaled.extend((t / s_prior, r) for t, r in train)
        m_user = _fit_S(
            HierarchicalMemoryModel(PopulationParams(log_mean=0.0, log_std=0.5)),
            rescaled,
        )

        for technique, (train, heldout) in usable.items():
            S_prior = prior_stability_days(technique)
            S_personal = _fit_S(model, train)
            S_person = S_prior * m_user

            for t, r_true in heldout:
                prior_s.errors.append(_retention(t, S_prior) - r_true)
                person_s.errors.append(_retention(t, S_person) - r_true)
                personal_s.errors.append(_retention(t, S_personal) - r_true)

    return {"PRIOR": prior_s, "PERSON": person_s, "PERSONAL": personal_s}


def paired_bootstrap(
    a: Scores, b: Scores, n_boot: int = 2000, seed: int = 0
) -> tuple[float, float]:
    """(mean MAE improvement of `a` over `b`, fraction of resamples where a wins).

    Paired because both predictors were scored on the exact same points, and
    bootstrapped rather than t-tested because absolute-error distributions are
    skewed and bounded. The second number is a directional confidence, not a
    p-value, and should not be reported as one.
    """
    if a.n == 0 or a.n != b.n:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    ea, eb = np.abs(a.errors), np.abs(b.errors)
    idx = rng.integers(0, len(ea), size=(n_boot, len(ea)))
    diffs = eb[idx].mean(axis=1) - ea[idx].mean(axis=1)
    return float(np.mean(eb) - np.mean(ea)), float(np.mean(diffs > 0))


# ── Data sources ──────────────────────────────────────────────────────────────


def cells_from_db() -> list[Cell]:
    """Build cells from the live database.

    Imported lazily so the simulation path has no database dependency at all.
    """
    from database import RetentionCheck, SessionLocal, StudySession

    db = SessionLocal()
    try:
        sessions = db.query(StudySession).order_by(StudySession.created_at).all()
        checks = db.query(RetentionCheck).all()
        by_session: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for rc in checks:
            t = 1.0 if rc.check_type == "24h" else 7.0
            by_session[rc.session_id].append((t, float(rc.score)))

        grouped: dict[tuple[int, str], Cell] = {}
        for s in sessions:
            obs = by_session.get(s.id)
            if not obs:
                continue
            technique = s.technique.value if hasattr(s.technique, "value") else str(s.technique)
            key = (s.user_id, technique)
            cell = grouped.setdefault(key, Cell(s.user_id, technique))
            # Session order is already chronological; within a session, 24h
            # genuinely precedes 7d.
            cell.observations.extend(sorted(obs))
        return list(grouped.values())
    finally:
        db.close()


def simulate_cohort(
    n_users: int,
    sessions_per_technique: int,
    tau_technique: float,
    techniques: tuple[str, ...] = (
        "practice_testing",
        "spaced_repetition",
        "active_recall",
        "re_reading",
    ),
    sigma_person: float = 0.35,
    noise: float = 0.08,
    seed: int = 0,
) -> list[Cell]:
    """Generate a cohort with a KNOWN amount of per-person technique variation.

    log S[user, technique] = log S_prior[technique]
                             + Normal(0, sigma_person)      ← person is strong/weak overall
                             + Normal(0, tau_technique)     ← person × technique interaction

    `tau_technique` is the entire question. At tau = 0, which technique suits
    you is identical for everyone and per-technique personalisation has nothing
    to find — a correct evaluator must report no PERSONAL advantage there.
    Above zero, it should find it, given enough observations.
    """
    rng = np.random.default_rng(seed)
    cells: list[Cell] = []
    for user_id in range(n_users):
        person_offset = rng.normal(0.0, sigma_person)
        for technique in techniques:
            log_s = (
                math.log(prior_stability_days(technique))
                + person_offset
                + rng.normal(0.0, tau_technique)
            )
            S = math.exp(log_s)
            cell = Cell(user_id, technique)
            for _ in range(sessions_per_technique):
                for t in (1.0, 7.0):
                    r = _retention(t, S) + rng.normal(0.0, noise)
                    cell.observations.append((t, float(np.clip(r, 0.01, 1.0))))
            cells.append(cell)
    return cells


# ── Reporting ─────────────────────────────────────────────────────────────────


def report(scores: dict[str, Scores]) -> None:
    print(f"  held-out points: {scores['PRIOR'].n}")
    for name in ("PRIOR", "PERSON", "PERSONAL"):
        s = scores[name]
        print(f"    {name:<9} MAE {s.mae:.4f}   RMSE {s.rmse:.4f}")

    gain_person, conf_person = paired_bootstrap(scores["PERSON"], scores["PRIOR"])
    gain_pers, conf_pers = paired_bootstrap(scores["PERSONAL"], scores["PERSON"])
    print(
        f"    PERSON   over PRIOR :  MAE gain {gain_person:+.4f}"
        f"  (wins {conf_person:.0%} of resamples)"
    )
    print(
        f"    PERSONAL over PERSON:  MAE gain {gain_pers:+.4f}"
        f"  (wins {conf_pers:.0%} of resamples)"
    )
    verdict = (
        "per-technique personalisation predicts better"
        if conf_pers > 0.95
        else "no detectable per-technique personalisation advantage"
    )
    print(f"    -> {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", action="store_true", help="evaluate the live database")
    ap.add_argument("--simulate", action="store_true", help="run the power study")
    ap.add_argument("--holdout", type=float, default=0.3)
    ap.add_argument(
        "--seeds", type=int, default=3,
        help="synthetic cohorts averaged per cell of the power table",
    )
    args = ap.parse_args()

    if args.db:
        cells = cells_from_db()
        users = len({c.user_id for c in cells})
        print(f"\nLive data: {users} users, {len(cells)} (user, technique) cells")
        if users < 5:
            print("  WARNING: far too few users to read anything into this.")
        report(evaluate(cells, args.holdout))
        return

    if args.simulate:
        print("\nPower study — how much data before a real effect becomes visible?\n")
        print("tau = between-person spread in per-technique stability (log units).")
        print("      tau=0   everyone is suited by the same techniques")
        print("      tau=0.2 modest individual differences")
        print("      tau=0.6 the strong version of the personalisation thesis\n")
        print("Cell shows how often PERSONAL beat PERSON across bootstrap resamples.")
        print("Read >95% as detected. The tau=0 row must stay low — that row is")
        print("the false-positive check, not a result.\n")

        configs = ((10, 3), (10, 6), (10, 12), (20, 12))
        header = "  tau  " + "".join(
            f"{n}u x {k}s".rjust(12) for n, k in configs
        )
        print(header)
        print("  " + "-" * (len(header) - 2))
        for tau in (0.0, 0.2, 0.4, 0.6):
            row = f"  {tau:.1f}  "
            for n_users, per_tech in configs:
                # Averaged over several synthetic cohorts. One cohort per cell
                # is noisy enough to print a non-monotonic table, which reads
                # as a bug in the method rather than as sampling variation.
                confs = []
                for seed in range(args.seeds):
                    cells = simulate_cohort(n_users, per_tech, tau, seed=seed + 1)
                    scores = evaluate(cells, args.holdout)
                    _, conf = paired_bootstrap(scores["PERSONAL"], scores["PERSON"])
                    confs.append(conf)
                row += f"{float(np.mean(confs)):>11.0%}"
            print(row)
        print("\n  u = users, s = sessions per technique (each gives a 24h + 7d check)")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
