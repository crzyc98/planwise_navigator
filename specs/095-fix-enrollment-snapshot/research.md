# Phase 0 Research: Voluntary Enrollment Not Reflected in Snapshot

**Date**: 2026-06-15 | **Branch**: `095-fix-enrollment-snapshot`

This investigation was performed against the live `dbt/simulation.duckdb` (3-year run, 2025–2027). All findings below are evidence-backed, not hypothetical.

## Symptom reproduction

Counts of voluntary-category enrollees vs. how they appear in `fct_workforce_snapshot` (same year):

| Year | Category | Enrollees | Snapshot participating | Snapshot rate > 0 |
|------|----------|-----------|------------------------|-------------------|
| 2025 | voluntary_enrollment | 541 | 541 | 541 |
| 2025 | proactive_voluntary | 587 | 587 | 587 |
| 2025 | year_over_year_voluntary | 18 | 18 | 18 |
| **2026** | **voluntary_enrollment** | **59** | **0** | **0** |
| 2026 | proactive_voluntary | 705 | 705 | 705 |
| **2026** | **year_over_year_voluntary** | **1** | **0** | **0** |
| 2027 | voluntary_enrollment | 26 | 26 | 26 |
| 2027 | proactive_voluntary | 731 | 731 | 731 |
| 2027 | year_over_year_voluntary | 2 | 2 | 2 |

The defect is **intermittent and year-specific**: it hits `voluntary_enrollment` and `year_over_year_voluntary` in **2026 only**, while `proactive_voluntary` (new hires) is always fine.

## Decision 1 — Root cause

**Decision**: The defect originates in `int_deferral_rate_state_accumulator.sql`, in the subsequent-year (`{% else %}`) branch's `is_enrolled_flag` derivation and the corresponding `WHERE` filter.

**Evidence**: For the 59 failing 2026 voluntary enrollees:
- `int_enrollment_state_accumulator` (the *enrollment* accumulator) correctly shows `enrollment_status = true`, `enrollment_method = voluntary`.
- `int_deferral_rate_state_accumulator` (the *deferral* accumulator) has **no row at all** for them in 2026 (`current_deferral_rate` is NULL via outer join).
- All 59 had a 2025 deferral-accumulator row with `is_enrolled_flag = false` (present-but-unenrolled).
- `fct_workforce_snapshot` derives `participation_status` (`dsa.current_deferral_rate > 0 → 'participating'`) and `current_deferral_rate` from the deferral accumulator (`int_deferral_rate_state_accumulator` aliased `dsa`). With no accumulator row, both default to not-participating / 0.0, and no match is produced.

**The exact flaw** (lines 465–468 and 504–506):

```sql
-- is_enrolled_flag (subsequent years)
CASE
  WHEN oo.employee_id IS NOT NULL THEN false
  ELSE COALESCE(ps.is_enrolled_flag, ne.employee_id IS NOT NULL, false)   -- BUG
END AS is_enrolled_flag,
...
WHERE (ps.employee_id IS NOT NULL OR ne.employee_id IS NOT NULL OR ce.employee_id IS NOT NULL OR mr.employee_id IS NOT NULL)
  AND COALESCE(ps.is_enrolled_flag, ne.employee_id IS NOT NULL, false) = true   -- BUG
```

`COALESCE` returns the first **non-NULL** value. For an employee whose prior-year row exists with `ps.is_enrolled_flag = false`, the COALESCE returns `false` and never evaluates the `ne.employee_id IS NOT NULL` term — even though `ne` (a current-year enrollment) is present. The `WHERE ... = true` filter then excludes the employee from the accumulator entirely.

**Why year-specific** (this confirms, not just explains, the root cause):
- **First year (2025)** uses the separate `first_year_state` branch whose `WHERE COALESCE(w.employee_id, he.employee_id) IS NOT NULL` includes **all** workforce employees, so unenrolled employees get a 2025 row with `is_enrolled_flag = false`.
- **Subsequent years** exclude unenrolled employees (`is_enrolled_flag = true` filter), so an employee unenrolled in 2026 has **no** 2026 accumulator row.
- Therefore the stale-`false` collision only happens when prior-year state contains an `is_enrolled_flag = false` row — which is **only** the first year. An employee newly enrolling in **2026** collides with their 2025 `false` row → dropped. An employee newly enrolling in **2027** had no 2026 row (`ps` is NULL) → `COALESCE(NULL, true, false) = true` → included. This matches the table exactly (2026 broken, 2027 fine).
- `proactive_voluntary` are new hires (no prior-year row) → always `ps` NULL → always fine.

## Decision 2 — Fix strategy

**Decision**: Make current-year enrollment authoritative over stale prior-year unenrolled state, with opt-out taking highest precedence. Replace the COALESCE in both the `is_enrolled_flag` expression and the `WHERE` clause with explicit precedence:

```sql
CASE
  WHEN oo.employee_id IS NOT NULL THEN false        -- opt-out this year wins
  WHEN ne.employee_id IS NOT NULL THEN true         -- new enrollment this year
  ELSE COALESCE(ps.is_enrolled_flag, false)         -- otherwise carry forward
END
```

**Rationale**: This is the minimal, semantically-correct change. A current-year enrollment event is definitive evidence the employee is enrolled; it must not be overridden by a prior-year `false`. Opt-out precedence preserves FR-008's year-end "opt-out wins" rule. Carry-forward (`ps.is_enrolled_flag`) remains the default when there is no current-year activity, preserving FR-007 persistence.

**Alternatives considered**:
- *Stop emitting `is_enrolled_flag = false` rows in the first year* (make first-year `WHERE` match subsequent years). Rejected: the E096 fix deliberately includes all workforce employees in year 1 so census/non-enrolled employees appear in the snapshot; removing it risks regressions elsewhere and is broader than necessary.
- *Fix only the `WHERE` clause.* Rejected: the `is_enrolled_flag` output column would still be wrong (`false`) for these employees even if they passed the filter, corrupting downstream `is_enrolled` semantics.
- *Re-derive participation in the snapshot from the enrollment-state accumulator instead of the deferral accumulator.* Rejected: larger blast radius, and the deferral accumulator must be correct anyway because contributions and match read from it.

## Decision 3 — Propagation scope (one fix, three symptoms)

**Decision**: The single accumulator fix resolves deferral rate, participation status, **and** match without touching downstream models.

**Evidence — confirmed dependency chain**:
- `int_employee_contributions` reads `current_deferral_rate` from `int_deferral_rate_state_accumulator` (documented as "S042-01: Source of Truth Architecture Fix").
- `int_employee_match_calculations` reads `effective_annual_deferral_rate` and `annual_contribution_amount` from `int_employee_contributions`; `fct_employer_match_events` reads from `int_employee_match_calculations`.
- `fct_workforce_snapshot` reads `current_deferral_rate` / participation from the same accumulator.

Once the accumulator includes these employees with their correct rate, contributions are computed, match follows from contributions, and the snapshot shows participating — all consistent (FR-005).

## Decision 4 — FR-008 prorated same-year enroll-then-opt-out

**Decision**: Treat the partial-window contribution/match crediting as a **separate, deferred phase (Phase C)**, not part of the core fix.

**Evidence**: `int_employee_contributions` prorates `prorated_annual_compensation` by **employment** window (hire → termination) only; the contribution is `prorated_annual_compensation * deferral_rate` using the year-end accumulator rate. There is **no** enrollment-window proration. So an employee who enrolls mid-year and opts out later in the same year currently gets year-end rate (0 after opt-out) × full-year comp = $0 — they are **not** credited for the active window.

**Rationale**: The user's reported defect (US1/US2) is fully addressed by Phase A. FR-008's year-end *status* (opt-out wins, no stale rate) is also satisfied by Phase A. Only the *prorated contribution during the active window* is outstanding, and it requires new logic (deriving an active-enrollment fraction from enrollment/opt-out effective dates and applying it in the contribution model). This is a genuine edge case (same-year enroll **and** opt-out) and is best designed and reviewed on its own to avoid scope creep into the contribution engine.

**Alternatives considered**: Fold proration into Phase A. Rejected — it changes the contribution model's compensation-base semantics and warrants its own tests and review; bundling it would delay the high-value core fix.

## Decision 5 — Regression guard (FR-009/FR-010)

**Decision**: Add a permanent dbt data-quality test model (`dq_voluntary_enrollment_snapshot`) that returns offending rows (and thus fails) when any voluntarily enrolled, non-opted-out employee is absent from snapshot participation or carries a deferral rate inconsistent with their enrollment event. Register it as a dbt test so it runs in `dbt build`.

**Rationale**: Matches the established E080 pattern (validation models converted to dbt tests). The test must **fail on the current pre-fix DB** (proving it catches the bug) and **pass after the fix** (Red → Green), satisfying Constitution Principle III and FR-010's "fails the build" requirement.

**Alternatives considered**: A one-time manual check (rejected — spec clarification chose a permanent automated guard); a non-blocking warning (rejected — clarification chose build-failing).

## Open questions

None. All NEEDS CLARIFICATION items from the spec are resolved; root cause and fix are confirmed against live data.
