# CogPrint — The Science

> Every algorithmic choice in CogPrint's zero-LLM brain traces to the learning-
> science literature. This document is the map from code → citation. It exists so
> the product can make its claims **honestly** and defend them — earned trust is
> the entire moat (see COGPRINT_MEGAPROMPT.md). If code and this doc disagree, the
> code wins; update this doc.

## The one-paragraph summary

CogPrint models memory with the **Ebbinghaus forgetting curve**, estimates how
durably *you* retain material under each study technique using a **hierarchical
Bayesian** model (population prior → individual posterior), ranks techniques with
research-grounded **priors** you sharpen through use, schedules reviews with a
**spacing** algorithm, and recommends techniques with a **contextual bandit**. None
of it calls an LLM.

---

## 1. Forgetting curve — `personalization/forgetting_curve.py`, `review.py`

**Model:** retention decays exponentially with time, `R(t) = e^(−t/S)`, where `S`
is a per-technique memory *stability* (in days). Higher `S` ⇒ slower forgetting.

- **Ebbinghaus, H. (1885).** *Über das Gedächtnis.* The original forgetting curve.
- **Murre & Dros (2015),** "Replication and Analysis of Ebbinghaus' Forgetting
  Curve," *PLoS ONE* — modern confirmation of the exponential form.

## 2. Technique effectiveness ranking — `personalization/priors.py`

**Claim:** techniques differ reliably in how well they support long-term
retention; the *ordering* is robust even though absolute numbers vary by material
and learner. Priors encode this ordering (practice testing & spacing high →
rereading low) and are treated as **priors, not measurements** — flagged
`population_informed=False` until the learner's own data arrives.

- **Dunlosky, Rawson, Marsh, Nathan & Willingham (2013),** "Improving Students'
  Learning With Effective Learning Techniques," *Psychological Science in the
  Public Interest* 14(1). The backbone: utility ratings across 10 techniques —
  **practice testing** and **distributed practice** rated HIGH; elaborative
  interrogation & self-explanation MODERATE; **rereading**, highlighting,
  summarization LOW.
- **Roediger & Karpicke (2006),** "Test-Enhanced Learning," *Psychological
  Science* — the **testing effect**: retrieval practice beats restudy at delays.
- **Cepeda, Pashler, Vul, Wixted & Rohrer (2006),** "Distributed Practice in
  Verbal Recall Tasks," *Psychological Bulletin* — the **spacing effect**
  meta-analysis.
- **Bjork & Bjork (2011),** "Making Things Hard on Yourself, But in a Good Way:
  Creating Desirable Difficulties" — interleaving & generation.

## 3. Individual estimation — `personalization/hierarchical_memory.py`

**Model:** a hierarchical Bayesian estimate of each technique's stability `S`.
`log(S) ~ Normal(μ_pop, σ_pop)`; the per-user posterior `p(S | data, population)`
is sampled with Metropolis–Hastings MCMC. With little data the estimate shrinks
toward the population/prior mean; as retention checks accumulate the posterior
concentrates on the individual. Credible intervals quantify uncertainty (surfaced
so the product never shows false precision).

- Standard **empirical-Bayes / hierarchical modelling** (Gelman et al., *Bayesian
  Data Analysis*). The population prior is fit by MLE on all users' point
  estimates once ≥4 exist; before that, per-technique priors from §2 seed it.

## 4. Scheduling — `agents/study_planner.py`

**Model:** an Ebbinghaus-guided spaced-repetition scheduler (a DP/greedy
approximation to a retention-maximizing MDP). Next review is set where predicted
retention drops to a threshold: `Δt = S · ln(1/θ)`, θ = 0.85 — the SM-2 inter-
repetition interval expressed via Ebbinghaus.

- **SuperMemo SM-2 (Wozniak, 1990)** — the canonical spaced-repetition interval
  algorithm; CogPrint's is its Ebbinghaus-explicit form.
- **Material-aware matching:** `score(technique) = material_fit × effectiveness`.
  `material_fit` comes from the concept's (difficulty × type) context using the
  Dunlosky utility ordering; `effectiveness` is the learner's estimate (or the
  §2 prior at cold start). Material type is a *modulation* on top of the strong
  general effect — not a hard gate (guardrail: never over-claim material
  specificity).

## 5. Recommendation — `personalization/linucb.py`

**Model:** **LinUCB**, a contextual multi-armed bandit, balances exploiting the
technique that has worked against exploring under-sampled ones.

- **Li, Chu, Langford & Schapire (2010),** "A Contextual-Bandit Approach to
  Personalized News Article Recommendation," *WWW '10* — the LinUCB algorithm.

## 6. Material analysis — `agents/material_analyzer.py`

Pure NLP, no LLM: **TF-IDF** term weighting → **LSA** (truncated SVD) for latent
structure → **TextRank** (PageRank over a concept-similarity graph) for centrality
→ heuristic typing (factual|conceptual|procedural × foundational|intermediate|
advanced).

- **Salton & Buckley (1988),** term-weighting (TF-IDF).
- **Deerwester et al. (1990),** Latent Semantic Analysis.
- **Mihalcea & Tarau (2004),** "TextRank: Bringing Order into Texts," *EMNLP*.

---

## The honesty contract

1. Priors are **priors**. Anything shown from a prior-only state reads as an
   *early, research-based estimate*, and carries a confidence band.
2. The **ordering** of techniques is what the literature supports reliably;
   absolute 7-day retention numbers are calibrated interpretations, not quotes.
3. Uncertainty is **surfaced**, never hidden. At low N: "early read."
4. The brain is **backtested**: `tests/test_science_backtest.py` seeds synthetic
   learners whose true technique ranking matches the literature and asserts the
   full pipeline recovers that ranking. This is the regression test for the
   *intelligence itself*, not just the plumbing.
