# Decision needed: lock ONE retention-test schedule

**Status:** OPEN — scientific + architectural decision for Katchi and the UiO
advisor (Prof. Leila Ferguson, meeting ~19 June 2026). **Do not let a coding
agent resolve this unilaterally** — it changes what the study measures.

## The discrepancy

| Where | Schedule |
|---|---|
| Study materials (Google Forms) | test at **day 1, 5, 10, 30** |
| Backend code (this repo) | **immediate quiz + 24h + 7d** |

Until these match, any analysis that joins materials data with backend data is
ambiguous (different retention intervals = not comparable). This is the single
most important protocol fix before data collection starts.

## Why it is not just a config value

The intervals are baked into the **forgetting-curve math**, not only the
reminder schedule. The keys `"24h"`/`"7d"` and their day-coordinates `t=1.0`,
`t=7.0` are read directly by:

- `personalization/forgetting_curve.py` — OLS Ebbinghaus fit uses points at t=1, t=7
- `personalization/hierarchical_memory.py` — MCMC observations at t=1, t=7
- `personalization/linucb.py` — reward = 7d (gold) → 24h×0.85 → quiz×0.70
- `personalization/fingerprint_builder.py` — per-technique aggregation
- `personalization/serializer.py` — legacy narrative aggregation

`config.py` now centralises the **scheduling-facing** half (reminders +
input validation read `RETENTION_SCHEDULE`). The five files above still encode
the math and must be updated together if the schedule changes.

## The two options

### Option A — keep immediate / 24h / 7d (change the materials)
- ✅ Backend is already built and validated around it.
- ✅ Short window → faster data collection, less participant dropout.
- ❌ Only 2 delayed points → a 2-point curve fit (weaker individual curves).
- ❌ Requires rebuilding the Google Forms to test at 24h + 7d.

### Option B — adopt day 1 / 5 / 10 / 30 (change the code)
- ✅ 4 delayed points → much better forgetting-curve fits per technique
      (the individual-level stability claim in §4.2 is stronger with 4 points).
- ✅ 30-day point captures real long-term retention, which is the actual claim.
- ❌ Requires reworking the math in the 5 files above (new keys + day-coords;
      re-derive the LinUCB reward weighting; widen `check_type` column).
- ❌ Longer window per period × 3 periods + washouts → slower study.

## Recommendation to discuss (not a decision)
Option B is scientifically stronger (4 points beats 2 for curve stability, and
30 days is closer to what "retention" should mean), but costs a code rework and
a longer timeline. If the Jan 2027 deadline is tight, Option A ships sooner. Take
this table to the 19 June meeting and lock one; then:

1. Edit `config.py:RETENTION_SCHEDULE` to the chosen checkpoints.
2. If Option B, update the 5 `personalization/` files' keys + day-coordinates
   and re-derive the LinUCB reward weights; widen `database.py` `check_type`
   column if any key exceeds 10 chars.
3. Align the Google Forms to match.
4. Update `/export/study-data` columns (currently `retention_24h`, `retention_7d`).
