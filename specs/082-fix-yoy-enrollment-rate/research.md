# Research: Fix Year-over-Year Voluntary Enrollment Rate Override

**Date**: 2026-03-20
**Branch**: `082-fix-yoy-enrollment-rate`

## Research Questions & Findings

### RQ-1: How do the other two pathways apply `voluntary_enrollment_rate`?

**Decision**: Use the same `COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)` pattern.

**Rationale**: Both `int_voluntary_enrollment_decision.sql` (line 159) and `int_proactive_voluntary_enrollment.sql` (line 218) use an identical pattern:

```sql
(base_enrollment_rate * income_multiplier * job_level_multiplier *
 COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)) as final_enrollment_probability
```

The year-over-year CTE should multiply its `event_probability` by the same expression to maintain consistency.

**Alternatives considered**:
- Adding a separate `year_over_year_voluntary_rate` variable — rejected because it contradicts the "single dial" requirement and adds unnecessary complexity.
- Applying it in the WHERE clause instead of the probability — rejected because the other pathways apply it as a probability multiplier, not a filter.

---

### RQ-2: Where exactly in the year-over-year CTE should the multiplier be applied?

**Decision**: Multiply the final probability expression (after age × income × tenure multipliers) by `voluntary_enrollment_rate`.

**Rationale**: The year-over-year CTE in `int_enrollment_events.sql` (lines 553-569) calculates `event_probability` as:

```sql
(age_base_rate * income_multiplier * tenure_multiplier) as event_probability
```

The fix adds the voluntary enrollment rate as a fourth multiplicative factor:

```sql
(age_base_rate * income_multiplier * tenure_multiplier *
 COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)) as event_probability
```

This mirrors the pattern in the other two pathways. The probability is then used in the hash-based selection WHERE clause (lines 584-602), so scaling the probability automatically reduces the number of selected employees.

**Alternatives considered**:
- Applying the multiplier only in the WHERE clause — rejected because the probability value is also used for audit/reporting purposes.
- Using a separate CTE for the multiplier — rejected because it adds unnecessary complexity for a single multiplication.

---

### RQ-3: Does `voluntary_enrollment_rate` already flow to dbt as a variable?

**Decision**: Yes — no config/export changes needed.

**Rationale**: The variable is already exported in two places:
1. `export.py` line 105: `_set_if_not_none(dbt_vars, "voluntary_enrollment_rate", auto.voluntary_enrollment_rate, float)`
2. `export.py` line 212: `_set_if_not_none(dbt_vars, "voluntary_enrollment_rate", dc_plan_dict.get("voluntary_enrollment_rate"), float)`

And it has a default in `dbt_project.yml`: `voluntary_enrollment_rate: 1.0`

The year-over-year CTE in `int_enrollment_events.sql` can reference `{{ var('voluntary_enrollment_rate', 1.0) }}` with no additional plumbing.

---

### RQ-4: How should the fix interact with `year_over_year_conversion_enabled`?

**Decision**: The `voluntary_enrollment_rate` multiplier is applied **within** the year-over-year CTE, which is already gated by `year_over_year_conversion_enabled`. No interaction issues.

**Rationale**: The year-over-year CTE already has a filter:
```sql
WHERE {{ var('year_over_year_conversion_enabled', true) }} = true
```

When `year_over_year_conversion_enabled` is false, the CTE produces zero rows regardless of `voluntary_enrollment_rate`. When enabled, the multiplier scales probabilities. The two controls are orthogonal:
- `year_over_year_conversion_enabled`: binary on/off for the pathway
- `voluntary_enrollment_rate`: probability scaling for all voluntary pathways

---

### RQ-5: What test should validate the fix?

**Decision**: Add a dbt test that verifies year-over-year enrollment events are zero when `voluntary_enrollment_rate` is 0.

**Rationale**: The most critical acceptance criterion is SC-001: "voluntary enrollment rate at 0% produces exactly zero voluntary enrollment events." A dbt test can validate this by checking the `year_over_year_enrollment_events` CTE output (or the final `int_enrollment_events` model filtered to year-over-year source) when the variable is set to 0.

**Alternatives considered**:
- Python integration test — useful but slower; the dbt test is sufficient for the SQL-level fix.
- Testing at multiple rate values (25%, 50%) — good for manual validation but difficult to assert deterministically in a dbt test due to randomness.

## Summary

This is a straightforward, low-risk fix:
1. **One SQL change**: Add `* COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)` to the year-over-year probability calculation in `int_enrollment_events.sql`
2. **One dbt test**: Validate that year-over-year events are zero when `voluntary_enrollment_rate = 0`
3. **No config/UI/Python changes**: The variable already flows through the entire pipeline
