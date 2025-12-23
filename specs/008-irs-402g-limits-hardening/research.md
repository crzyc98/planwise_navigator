# Research: IRS 402(g) Limits Hardening

**Feature**: 008-irs-402g-limits-hardening
**Date**: 2025-12-23

## Research Task 1: Hardcoded Age Threshold Locations

### Question
Where exactly is `>= 50` hardcoded vs. using the seed file's `catch_up_age_threshold`?

### Findings

**Production SQL Models with Hardcoded Values:**

1. **`dbt/models/marts/fct_workforce_snapshot.sql:905`** - HARDCODED
   ```sql
   WHEN current_age >= 50 THEN 31000  -- Catch-up contribution limit
   ELSE 23500  -- Standard limit for under 50
   ```
   **Action Required**: Replace with reference to `irs_contribution_limits` seed.

2. **`dbt/tests/data_quality/test_employee_contributions_validation.sql:209`** - HARDCODED
   ```sql
   CASE WHEN current_age >= 50 THEN 31000 ELSE 23500 END
   ```
   **Action Required**: Replace with join to `irs_contribution_limits` seed.

**Production SQL Models Already Using Seed:**

1. **`dbt/models/intermediate/events/int_employee_contributions.sql`** - ✅ CORRECT
   - Lines 43, 54, 220, 229, 238, 246, 251, 276 all use `il.catch_up_age_threshold`
   - Joins to `irs_contribution_limits` seed correctly

2. **`dbt/tests/data_quality/test_employee_contributions.sql`** - ✅ CORRECT
   - Lines 47-49 join to `irs_contribution_limits` and use `catch_up_age_threshold`

3. **`dbt/models/marts/data_quality/dq_contribution_audit_trail.sql`** - ✅ CORRECT
   - Uses `catch_up_age_threshold` from seed

4. **`dbt/models/marts/data_quality/dq_employee_contributions_simple.sql`** - ✅ CORRECT
   - Uses `catch_up_age_threshold` from seed

**Documentation Only (no action needed):**
- `docs/stories/S036-*.md` - Design documentation
- `docs/epics/E021_*.md` - Epic documentation
- `docs/stories/S073-*.md`, `S023-*.md`, `S024-*.md`, `S075-*.md`, `S080-*.md` - Story documentation

### Decision
Fix 2 production files with hardcoded values:
1. `fct_workforce_snapshot.sql` - Update to join with `config_irs_limits` seed
2. `test_employee_contributions_validation.sql` - Update to join with `config_irs_limits` seed

### Rationale
These are the only production code files with hardcoded age thresholds. All other hardcoded values are in documentation which doesn't affect runtime behavior.

---

## Research Task 2: Hypothesis Best Practices for Contribution Limits

### Question
What are best practices for property-based testing of contribution limit invariants?

### Findings

**Property-Based Testing Strategy:**

1. **Core Invariant Property**
   ```python
   @given(
       age=st.integers(min_value=18, max_value=75),
       compensation=st.decimals(min_value=0, max_value=5_000_000, places=2),
       deferral_rate=st.decimals(min_value=0, max_value=1, places=4),
       plan_year=st.integers(min_value=2025, max_value=2035)
   )
   def test_contribution_never_exceeds_limit(age, compensation, deferral_rate, plan_year):
       limits = get_limits_for_year(plan_year)
       applicable_limit = limits.catch_up_limit if age >= limits.catch_up_age else limits.base_limit
       contribution = calculate_contribution(compensation, deferral_rate, applicable_limit)
       assert contribution <= applicable_limit
   ```

2. **Edge Case Strategies**
   - `st.just(0)` for zero compensation/deferral rate
   - `st.just(50)` combined with `st.sampled_from([49, 50, 51])` for age boundary
   - `st.decimals(min_value=0.99, max_value=1.0)` for near-max deferral rates

3. **Test Configuration**
   ```python
   @settings(
       max_examples=10000,  # Per spec requirement
       deadline=timedelta(seconds=60),  # Performance goal
       suppress_health_check=[HealthCheck.too_slow]
   )
   ```

### Decision
Implement property-based tests with:
1. Core invariant: `contribution <= applicable_limit` for all inputs
2. Flag accuracy property: `irs_limit_applied == (requested > applicable_limit)`
3. Boundary tests: Age threshold edge cases (49, 50, 51)
4. Use `@settings(max_examples=10000)` per spec requirement

### Rationale
Hypothesis is already in project dependencies. The strategy covers all functional requirements while maintaining <60s execution time.

---

## Research Task 3: Seed File Reference Updates

### Question
Which dbt models reference `irs_contribution_limits` and need updating after rename?

### Findings

**Files Referencing `irs_contribution_limits`:**

| File | Line(s) | Update Required |
|------|---------|-----------------|
| `dbt/models/intermediate/events/int_employee_contributions.sql` | 44, 55 | Yes - `{{ ref('irs_contribution_limits') }}` → `{{ ref('config_irs_limits') }}` |
| `dbt/tests/data_quality/test_employee_contributions.sql` | 48 | Yes |
| `dbt/tests/data_quality/test_employee_contributions_validation.sql` | 102 | Yes |
| `dbt/models/marts/data_quality/dq_contribution_audit_trail.sql` | TBD | Yes |
| `dbt/models/marts/data_quality/dq_compliance_monitoring.sql` | TBD | Yes |
| `dbt/models/marts/data_quality/dq_employee_contributions_simple.sql` | TBD | Yes |

**dbt_project.yml Updates:**
- No explicit seed configuration needed if using default naming convention
- May need to add `config_irs_limits` alias if original name is referenced elsewhere

### Decision
1. Rename file: `irs_contribution_limits.csv` → `config_irs_limits.csv`
2. Update all 6 model/test files with new `{{ ref('config_irs_limits') }}`
3. Run `dbt seed --threads 1` to load renamed seed
4. Run `dbt run --threads 1` to verify no broken references

### Rationale
Clean rename with all references updated ensures no runtime failures. The rename follows the existing `config_*` naming convention for configuration seeds.

### Alternatives Considered

1. **Keep original name**: Rejected - inconsistent with `config_age_bands.csv`, `config_tenure_bands.csv` naming pattern
2. **Create alias in dbt_project.yml**: Rejected - adds unnecessary complexity; clean rename is simpler
3. **Deprecate old name gradually**: Rejected - no external consumers; internal-only change

---

## Summary

| Research Task | Decision | Impact |
|---------------|----------|--------|
| Hardcoded age locations | Fix 2 files | `fct_workforce_snapshot.sql`, `test_employee_contributions_validation.sql` |
| Hypothesis strategy | Core invariant + boundary tests | New test file with 10K examples |
| Seed reference updates | Rename + update 6 files | All `{{ ref('irs_contribution_limits') }}` → `{{ ref('config_irs_limits') }}` |

All research tasks completed. No NEEDS CLARIFICATION items remain.
