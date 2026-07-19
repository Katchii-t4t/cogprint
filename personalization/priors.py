"""
Research-derived population priors for the cognitive fingerprint (§2.1 cold-start).

Purpose
-------
Before a user has produced any retention data of their own, CogPrint should not
pretend to know nothing (flat priors) — the learning-science literature already
tells us a great deal about how well each technique retains, on average, across
hundreds of studies.  These priors make the brain useful from session zero:

  - The study planner scores `material_fit × effectiveness`; with no personal
    data, `effectiveness` now comes from here instead of a flat 0.70, so day-1
    recommendations are differentiated and research-defensible.
  - The hierarchical Bayesian model starts each technique's stability prior at
    the literature-implied value instead of one global default, then lets the
    user's own retention checks sharpen the posterior (population prior →
    individual posterior — textbook hierarchical Bayes).

Honesty rules (mirrors COGPRINT_MEGAPROMPT.md guardrail #3)
-----------------------------------------------------------
- These are *priors*, not measurements.  Anything surfaced to the user from a
  prior-only state must read as an early, research-based estimate
  (`population_informed=False` already flags this downstream).
- Once ≥4 real users provide OLS stability estimates, Empirical Bayes fitting
  from the actual cohort takes precedence (see fingerprint_builder step 5).
- The sigmas are deliberately broad: the literature ranks techniques reliably,
  but absolute 7-day retention varies hugely with material and learner.

Sources
-------
- Dunlosky, Rawson, Marsh, Nathan & Willingham (2013), "Improving Students'
  Learning With Effective Learning Techniques", PSPI 14(1) — utility ratings
  across 10 techniques; practice testing & distributed practice rated HIGH,
  rereading/summarization/highlighting rated LOW.
- Roediger & Karpicke (2006) — the testing effect (retrieval practice beats
  restudy at ≥2-day delays).
- Cepeda, Pashler, Vul, Wixted & Rohrer (2006) — distributed-practice
  meta-analysis (spacing improves long-term retention).
- Bjork & Bjork — desirable difficulties framework (interleaving, generation).

The absolute retention_7d numbers below are calibrated interpretations of that
ranking (same ordering used by seed_demo.py, which the pipeline demonstrably
recovers), not direct quotations — no single study reports one universal 7-day
number per technique.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TechniquePrior:
    """Population prior for one study technique."""

    retention_7d: float      # E[retention at 7 days] under this technique
    sigma: float             # breadth of that belief (std dev, retention units)
    dunlosky_utility: str    # "high" | "moderate" | "low" (PSPI 2013 rating)
    source: str              # citation shorthand

    @property
    def stability_days(self) -> float:
        """Ebbinghaus stability implied by the 7-day prior: R(t)=e^{-t/S}."""
        return -7.0 / math.log(self.retention_7d)


# Ordered by prior effectiveness — the Dunlosky (2013) ranking.
RESEARCH_PRIORS: dict[str, TechniquePrior] = {
    "practice_testing": TechniquePrior(
        retention_7d=0.85, sigma=0.12, dunlosky_utility="high",
        source="Dunlosky 2013 (high utility); Roediger & Karpicke 2006",
    ),
    "spaced_repetition": TechniquePrior(
        retention_7d=0.79, sigma=0.13, dunlosky_utility="high",
        source="Dunlosky 2013 (high utility); Cepeda et al. 2006",
    ),
    "active_recall": TechniquePrior(
        retention_7d=0.73, sigma=0.14, dunlosky_utility="high",
        source="Roediger & Karpicke 2006 (retrieval practice)",
    ),
    "elaborative_interrogation": TechniquePrior(
        retention_7d=0.68, sigma=0.15, dunlosky_utility="moderate",
        source="Dunlosky 2013 (moderate utility)",
    ),
    "interleaving": TechniquePrior(
        retention_7d=0.64, sigma=0.16, dunlosky_utility="moderate",
        source="Dunlosky 2013 (moderate utility); Bjork desirable difficulties",
    ),
    "mind_maps": TechniquePrior(
        retention_7d=0.58, sigma=0.17, dunlosky_utility="low",
        source="nearest Dunlosky analogues (summarization/imagery: low utility)",
    ),
    "re_reading": TechniquePrior(
        retention_7d=0.50, sigma=0.15, dunlosky_utility="low",
        source="Dunlosky 2013 (low utility); Roediger & Karpicke 2006 control arm",
    ),
}

# Fallbacks for a technique string we don't recognise (defensive; matches the
# planner's old flat prior and the hierarchical model's old global default).
_DEFAULT_EFFECTIVENESS = 0.70
_DEFAULT_STABILITY_DAYS = 14.0


def prior_effectiveness(technique: str) -> float:
    """Research-prior expected 7-day retention for a technique (planner units)."""
    p = RESEARCH_PRIORS.get(technique)
    return p.retention_7d if p else _DEFAULT_EFFECTIVENESS


def prior_stability_days(technique: str) -> float:
    """Research-prior Ebbinghaus stability S (days) for a technique."""
    p = RESEARCH_PRIORS.get(technique)
    return p.stability_days if p else _DEFAULT_STABILITY_DAYS
