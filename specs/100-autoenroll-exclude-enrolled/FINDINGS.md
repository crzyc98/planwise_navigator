# Findings: GitHub issue #318 (auto-enroll re-enrolling existing participants)

**Date**: 2026-06-20
**Outcome**: Not a live bug. The reported defect does not reproduce on the
event-generation path. The model the issue cited was orphaned dead code, which has
been removed. A live-path regression test was added to lock in the correct behavior.

## What #318 claimed

With auto-enrollment scope `all_eligible_employees` and a permissive hire-date
cutoff, already-contributing employees (census pre-enrolled, or enrolled in a prior
year) are swept into auto-enrollment and reset to the default deferral rate (~2%),
destroying their higher existing rate. The issue pointed at
`int_enrollment_decision_matrix`.

## What we found

1. **The cited model is orphaned dead code.** `int_enrollment_decision_matrix`,
   `int_enrollment_timing_coordination`, and `int_auto_enrollment_window_determination`
   form a chain that **nothing downstream references** and that the real pipeline
   never builds (the tables do not exist in a freshly simulated database). The
   initial "proof" that #318 was real had read this model statically without
   confirming it feeds `fct_yearly_events` — it does not.

2. **The live path already guards against #318.** Auto-enrollment events are
   generated in `int_enrollment_events.sql`, which gates on `was_enrolled_previously`
   (built from census `is_enrolled_flag` + prior-year enrollment events) and emits
   auto events only `WHERE is_already_enrolled = false`. The live voluntary path
   (`int_voluntary_enrollment_decision`) independently filters
   `WHERE is_currently_enrolled = false` (census + prior-year accumulator).

3. **Empirical confirmation.** A 3-year isolated simulation under the worst case
   (scope `all_eligible_employees`, hire-date cutoff `1900-01-01`, default 2%):
   - **0** census-enrolled employees received an auto-enrollment event, in any year.
   - All 5,698 census savers with a deferral rate above the default are correctly
     flagged enrolled in `int_employee_compensation_by_year`.
   - The deferral-rate decreases initially mistaken for the bug were
     `deferral_match_response` events ("Match response: 10.0% → 6.0%, target 6.0%"),
     a separate, intended behavioral model — not auto-enrollment.

## Actions taken

- **Deleted** the orphaned dead-code chain (3 models) and their `schema.yml`
  entries: `int_enrollment_decision_matrix`, `int_enrollment_timing_coordination`,
  `int_auto_enrollment_window_determination`. (These were the source of the
  confusion — they look authoritative and even match the issue text, but drive
  nothing.)
- **Added** `tests/test_existing_participant_not_auto_enrolled.py` — an
  `integration` regression guard asserting against the live `fct_yearly_events` /
  `fct_workforce_snapshot` that no census-enrolled employee is ever auto-swept and
  that legitimate auto-enrollment still occurs. Passes against the worst-case run.
- No change to the live enrollment logic was required.

## Recommendation for #318

Close as **already mitigated / not reproducible**, citing this document. If the
`deferral_match_response` downward adjustment for over-savers is itself considered
undesirable, that is a distinct behavioral question and warrants its own issue.

## How to re-verify

```bash
DATABASE_PATH=/tmp/ae318/sim_all_eligible.duckdb  # or any simulated DB
planalign simulate 2025-2027   # default config also fine; worst case uses all_eligible + early cutoff
pytest tests/test_existing_participant_not_auto_enrolled.py -v
```
