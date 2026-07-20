"""
Hierarchical Bayesian memory model for CogPrint.

Architecture — Empirical Bayes approximation to full hierarchical Bayes:

  Population level  (estimated via MLE from all users):
    μ_pop, σ_pop  ← mean and std of log(S_i) across the cohort

  Individual level:
    log(S_i) ~ Normal(μ_pop, σ_pop)     ← shrinks toward population mean

  Observation level:
    R(t) = exp(-t / S_i)                ← Ebbinghaus forgetting curve
    R_obs ~ Normal(R(t), σ_noise)        ← Gaussian measurement noise

  Inference: Metropolis-Hastings MCMC
    Proposal: log-normal random walk
      S_new = S_curr · exp(Normal(0, σ_step))
    This proposal is symmetric in log-space, so no Jacobian correction needed.

Why Empirical Bayes instead of full hierarchical Bayes:
  Full Bayes would place hyperpriors on μ_pop and σ_pop and sample the entire
  hierarchy jointly (e.g. via Gibbs or HMC). For a pilot study with < 50
  participants, Empirical Bayes is a well-established and computationally
  tractable approximation — it removes one level of the hierarchy while
  preserving the key benefit: shrinkage of sparse individual estimates
  toward the cohort mean.

Key benefit over per-user OLS:
  A user with only 2 retention observations has a noisy S estimate.
  The population prior shrinks it toward the cohort mean proportionally
  to how uninformative the individual data is — exactly Bayesian shrinkage.
  As more data accumulates, the posterior concentrates and the prior matters less.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

# ── Hyperparameters ────────────────────────────────────────────────────────────

_SIGMA_NOISE  = 0.08   # standard deviation of Gaussian measurement noise on R
_N_SAMPLES    = 2000   # MCMC posterior samples kept (after burn-in)
_BURN_IN      = 600    # samples discarded during chain warm-up
_PROPOSAL_STD = 0.28   # log-scale random-walk step size
_S_MIN        = 0.5    # hard lower bound on stability (days)
_S_MAX        = 365.0  # hard upper bound on stability (days)


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class PopulationParams:
    """
    Hyperparameters of the log-normal population prior on S.
    S ~ LogNormal(log_mean, log_std)  ↔  log(S) ~ Normal(log_mean, log_std)
    """
    log_mean: float = math.log(14.0)  # prior centered at ~14 days
    log_std:  float = 0.55            # broad prior — ≈ factor-of-2 uncertainty


@dataclass
class PosteriorSummary:
    """
    Summary statistics of the per-user posterior p(S | data, population).
    All values are in days.
    """
    mean:               float   # posterior mean E[S | data]
    median:             float   # posterior median (robust to skew)
    std:                float   # posterior standard deviation
    ci_lower:           float   # 2.5th percentile  } 95% credible
    ci_upper:           float   # 97.5th percentile } interval
    n_samples:          int     # effective posterior samples used
    population_informed: bool   # True when individual data was available


# ── Model ──────────────────────────────────────────────────────────────────────

class HierarchicalMemoryModel:
    """
    Empirical Bayes hierarchical Ebbinghaus model.

    Typical usage
    -------------
    # Step 1 — update population hyperparameters from all users' data
    model = HierarchicalMemoryModel()
    model.fit_population(all_s_point_estimates)

    # Step 2 — compute per-user posterior
    summary = model.fit_user([(1.0, 0.82), (7.0, 0.61)])
    print(f"S = {summary.mean:.1f}d  95% CI: [{summary.ci_lower:.1f}, {summary.ci_upper:.1f}]")
    """

    def __init__(self, pop: Optional[PopulationParams] = None) -> None:
        self.pop = pop or PopulationParams()
        # True once fit_population() succeeds on real cohort data. While False,
        # callers may seed self.pop with research-derived per-technique priors
        # (personalization/priors.py) — Empirical Bayes from the actual cohort
        # always takes precedence once available.
        self.population_fitted = False

    # ── Population fitting ─────────────────────────────────────────────────────

    def fit_population(self, s_estimates: list[float]) -> None:
        """
        Update population hyperparameters via MLE on log-transformed point
        estimates of S collected from all users in the study.

        Requires at least 4 valid estimates; otherwise keeps default priors.

        Parameters
        ----------
        s_estimates : list of per-user point estimates of S (days).
            Typically the posterior median or OLS estimate from each user.
        """
        valid = [s for s in s_estimates if _S_MIN < s < _S_MAX]
        if len(valid) < 4:
            return  # not enough data — keep default priors

        log_s = np.log(np.array(valid, dtype=float))
        self.pop.log_mean = float(np.mean(log_s))
        # Floor on log_std prevents a degenerate prior that over-shrinks
        self.pop.log_std  = max(0.15, float(np.std(log_s)))
        self.population_fitted = True

    # ── Log-probability components ─────────────────────────────────────────────

    def _log_prior(self, S: float) -> float:
        """
        Log-normal prior log p(S):
          p(S) = (1 / S σ √2π) exp(−(log S − μ)² / 2σ²)
        The (1/S) term arises from the change of variables log S → S.
        """
        if S <= 0:
            return -math.inf
        log_s = math.log(S)
        return (
            -log_s
            - (log_s - self.pop.log_mean) ** 2 / (2.0 * self.pop.log_std ** 2)
        )

    def _log_likelihood(
        self, S: float, obs: list[tuple[float, float]]
    ) -> float:
        """
        Gaussian likelihood:
          R_obs_i ~ Normal(exp(−t_i / S), σ_noise)
          log p(data | S) = Σ_i  −½ ((R_obs_i − exp(−t_i/S)) / σ_noise)²

        Parameters
        ----------
        obs : [(t_days, R_observed), ...]
        """
        ll = 0.0
        for t, R in obs:
            R_pred = math.exp(-t / S)
            ll += -0.5 * ((R - R_pred) / _SIGMA_NOISE) ** 2
        return ll

    def _log_posterior(
        self, S: float, obs: list[tuple[float, float]]
    ) -> float:
        return self._log_prior(S) + self._log_likelihood(S, obs)

    # ── MCMC ───────────────────────────────────────────────────────────────────

    def _run_mcmc(
        self, obs: list[tuple[float, float]]
    ) -> np.ndarray:
        """
        Metropolis-Hastings sampler with log-normal random-walk proposal.

        Proposal: log S_new = log S_curr + Normal(0, σ_step)
          → S_new = S_curr · exp(ε),  ε ~ Normal(0, σ_step)

        Because the proposal is symmetric in log-space, the Hastings
        correction cancels and the acceptance probability simplifies to:

          α = min(1, p(S_new | data) / p(S_curr | data))

        Implementation notes (same math as _log_posterior, restated inline):
          * The current state's log-posterior is carried across iterations,
            so each step evaluates the posterior once (for the proposal)
            instead of twice.
          * All proposal/uniform draws are generated in one batch up front —
            per-step RNG calls dominate otherwise.
          * The likelihood loops over plain Python tuples for the small
            observation counts typical here (a session contributes ≤ 2
            points); NumPy's per-call overhead only pays off once the
            observation list is large, so big lists switch to array math.

        Returns array of posterior samples (burn-in already discarded).
        """
        rng     = np.random.default_rng()
        n_steps = _BURN_IN + _N_SAMPLES

        mu, sigma      = self.pop.log_mean, self.pop.log_std
        inv_two_var    = 1.0 / (2.0 * sigma * sigma)
        inv_noise_var  = 1.0 / (_SIGMA_NOISE * _SIGMA_NOISE)

        if len(obs) <= 24:
            obs_t = tuple(obs)

            def log_post(S: float) -> float:
                log_s = math.log(S)
                lp    = -log_s - (log_s - mu) ** 2 * inv_two_var
                acc   = 0.0
                for t, R in obs_t:
                    d = R - math.exp(-t / S)
                    acc += d * d
                return lp - 0.5 * acc * inv_noise_var
        else:
            t_arr = np.array([t for t, _ in obs], dtype=float)
            r_arr = np.array([R for _, R in obs], dtype=float)

            def log_post(S: float) -> float:
                log_s = math.log(S)
                lp    = -log_s - (log_s - mu) ** 2 * inv_two_var
                resid = r_arr - np.exp(-t_arr / S)
                return lp - 0.5 * float(resid @ resid) * inv_noise_var

        eps    = rng.normal(0.0, _PROPOSAL_STD, n_steps).tolist()
        log_u  = np.log(rng.uniform(size=n_steps)).tolist()

        S_cur  = math.exp(mu)   # initialise at prior mean
        lp_cur = log_post(S_cur)
        samples = np.empty(_N_SAMPLES, dtype=float)

        for step in range(n_steps):
            S_prop  = S_cur * math.exp(eps[step])
            lp_prop = log_post(S_prop)

            if log_u[step] < lp_prop - lp_cur:
                S_cur, lp_cur = S_prop, lp_prop

            if step >= _BURN_IN:
                samples[step - _BURN_IN] = S_cur

        return samples

    # ── Public API ─────────────────────────────────────────────────────────────

    def fit_user(
        self,
        observations: list[tuple[float, float]],
    ) -> PosteriorSummary:
        """
        Compute the posterior distribution over S for a single user.

        Parameters
        ----------
        observations : list of (t_days, R_observed)
            Retention checkpoints.  E.g. [(1.0, 0.82), (7.0, 0.61)]
            Pass an empty list for a user with no retention data yet.

        Returns
        -------
        PosteriorSummary
            Posterior mean, median, std, and 95% credible interval.
            When no observations are provided, samples are drawn from
            the population prior (useful for new users).
        """
        if not observations:
            # No individual data — sample from population prior
            samples = np.exp(
                np.random.normal(
                    self.pop.log_mean,
                    self.pop.log_std,
                    _N_SAMPLES,
                )
            )
            informed = False
        else:
            samples  = self._run_mcmc(observations)
            informed = True

        return PosteriorSummary(
            mean               = float(np.mean(samples)),
            median             = float(np.median(samples)),
            std                = float(np.std(samples)),
            ci_lower           = float(np.percentile(samples, 2.5)),
            ci_upper           = float(np.percentile(samples, 97.5)),
            n_samples          = int(len(samples)),
            population_informed = informed,
        )


# ── Convenience: collect observations from DB records ─────────────────────────

def observations_from_records(
    sessions,          # list[StudySession]
    retention_checks,  # list[RetentionCheck]
) -> list[tuple[float, float]]:
    """
    Build the [(t_days, R_observed)] list for a user from their DB records.
    Uses 24h (t=1.0) and 7d (t=7.0) checkpoints only — immediate quiz scores
    are excluded because they measure encoding quality, not forgetting rate.
    """
    rc_idx = {
        (rc.session_id, rc.check_type): rc.score
        for rc in retention_checks
    }
    obs: list[tuple[float, float]] = []
    for s in sessions:
        r24 = rc_idx.get((s.id, "24h"))
        r7d = rc_idx.get((s.id, "7d"))
        if r24 is not None:
            obs.append((1.0, float(r24)))
        if r7d is not None:
            obs.append((7.0, float(r7d)))
    return obs
