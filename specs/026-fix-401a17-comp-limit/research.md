# Research: Fix 401(a)(17) Compensation Limit

**Feature**: 026-fix-401a17-comp-limit
**Date**: 2026-01-22
**Status**: Complete

## Research Questions

### 1. IRS 401(a)(17) Limit Values by Year

**Decision**: Use IRS-published limits with reasonable extrapolation for future years

**Rationale**: The IRS publishes annual compensation limits. For simulation years beyond published data, we extrapolate at ~$10,000/year based on historical trends. This aligns with existing `config_irs_limits.csv` pattern for 402(g) limits.

**Verified Values**:
| Year | 401(a)(17) Compensation Limit |
|------|------------------------------|
| 2025 | $350,000 |
| 2026 | $360,000 |
| 2027 | $370,000 (projected) |
| 2028 | $380,000 (projected) |
| 2029 | $390,000 (projected) |
| 2030 | $400,000 (projected) |
| 2031 | $410,000 (projected) |
| 2032 | $420,000 (projected) |
| 2033 | $430,000 (projected) |
| 2034 | $440,000 (projected) |
| 2035 | $450,000 (projected) |

**Alternatives Considered**:
- Separate seed file for compensation limits: Rejected (adds complexity, limits already share same year key)
- Hardcoded values in SQL: Rejected (violates Type-Safe Configuration principle)

---

### 2. Match Calculation Integration Pattern

**Decision**: Add CTE to fetch limit, apply `LEAST()` in match cap calculation

**Rationale**: The existing `int_employee_match_calculations.sql` model uses a tiered match calculation pattern. The 401(a)(17) limit should cap the compensation base used in the match cap calculation (line 228), not the individual tier calculations. This preserves the existing tiered logic while limiting total employer exposure.

**Implementation Pattern**:
```sql
-- Add CTE to fetch current year limit
irs_compensation_limits AS (
    SELECT compensation_limit AS irs_401a17_limit
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = {{ simulation_year }}
),

-- In final_match CTE, modify line 228:
-- BEFORE: am.eligible_compensation * {{ match_cap_percent }}
-- AFTER:  LEAST(am.eligible_compensation, lim.irs_401a17_limit) * {{ match_cap_percent }}
```

**Key Observations from Code Review**:
- Line 228: `am.eligible_compensation * {{ match_cap_percent }}` - match cap calculation
- Line 235: Same pattern repeated for eligibility-filtered amount
- Service-based mode (line 128): Uses `ec.eligible_compensation` directly - also needs capping

**Alternatives Considered**:
- Cap at employee_contributions CTE: Rejected (affects deferral calculations upstream)
- Cap in tiered_match CTE: Rejected (would incorrectly affect tier boundary calculations)

---

### 3. Core Contribution Integration Pattern

**Decision**: Add CTE to fetch limit, apply `LEAST()` in core contribution calculation

**Rationale**: The existing `int_employer_core_contributions.sql` uses a similar pattern. The compensation base used in the core contribution calculation (line 263) should be capped.

**Implementation Pattern**:
```sql
-- Add CTE to fetch current year limit
irs_compensation_limits AS (
    SELECT compensation_limit AS irs_401a17_limit
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = {{ simulation_year }}
),

-- In core_contributions CTE, modify line 263:
-- BEFORE: COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation)
-- AFTER:  LEAST(COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation), lim.irs_401a17_limit)
```

**Key Observations from Code Review**:
- Line 263: Compensation used for core calculation
- Line 275-303: Same pattern repeated in contribution rate calculation
- Uses CROSS JOIN pattern to access single-row limit CTE

**Alternatives Considered**:
- Pass limit as dbt variable: Rejected (requires orchestrator changes, less transparent)
- Create macro for capped compensation: Considered for future DRY refactor, but adds complexity for 2-location fix

---

### 4. Prorated Compensation Handling

**Decision**: Apply 401(a)(17) limit to the already-prorated compensation amount

**Rationale**: For mid-year hires, compensation is already prorated based on hire date. The 401(a)(17) limit applies to annual compensation, but the IRS allows proration for short-year employees. We apply `LEAST(prorated_compensation, irs_401a17_limit)` which effectively caps both:
1. Full-year employees: capped at annual limit
2. Mid-year employees: capped at annual limit (but will naturally be below due to proration)

**Edge Case Analysis**:
- Employee earning $1M/year hired July 1: Prorated comp = $500K, capped at $360K (2026)
- Employee earning $300K/year hired July 1: Prorated comp = $150K, no cap applied (below $360K)
- Employee earning $400K/year full year: Capped at $360K

This behavior is IRS-compliant and simpler than proportionally prorating the limit.

**Alternatives Considered**:
- Proportionally prorate the 401(a)(17) limit: Rejected (more complex, not required by IRS for short years)

---

### 5. Audit Trail Field Design

**Decision**: Add `irs_401a17_limit_applied` boolean field to track when capping occurred

**Rationale**: Constitution Principle IV (Enterprise Transparency) requires audit visibility. Adding a boolean flag is the simplest approach that enables compliance verification.

**Field Specification**:
- Name: `irs_401a17_limit_applied`
- Type: BOOLEAN
- Logic: `eligible_compensation > irs_401a17_limit`
- Location: Both `int_employee_match_calculations.sql` and `int_employer_core_contributions.sql` output

**Alternatives Considered**:
- Store original uncapped amount: Already available via `eligible_compensation` field
- Store applied limit amount: Redundant (can be looked up from config_irs_limits)

---

### 6. dbt Test Pattern

**Decision**: Create singular test that returns violation rows (dbt convention)

**Rationale**: dbt singular tests pass when they return zero rows. The test queries for any match or core contribution that exceeds the 401(a)(17) capped maximum.

**Test Pattern**:
```sql
-- Returns rows that violate the constraint (test passes if 0 rows)
WITH irs_limits AS (
    SELECT limit_year, compensation_limit
    FROM {{ ref('config_irs_limits') }}
),
match_violations AS (
    SELECT m.employee_id, m.simulation_year, 'match' AS violation_type,
           m.employer_match_amount AS amount,
           l.compensation_limit * 0.04 AS max_allowed  -- 4% cap
    FROM {{ ref('int_employee_match_calculations') }} m
    JOIN irs_limits l ON m.simulation_year = l.limit_year
    WHERE m.employer_match_amount > l.compensation_limit * 0.04 + 0.01
),
core_violations AS (
    SELECT c.employee_id, c.simulation_year, 'core' AS violation_type,
           c.employer_core_amount AS amount,
           l.compensation_limit * 0.02 AS max_allowed  -- 2% default
    FROM {{ ref('int_employer_core_contributions') }} c
    JOIN irs_limits l ON c.simulation_year = l.limit_year
    WHERE c.employer_core_amount > l.compensation_limit * 0.02 + 0.01
)
SELECT * FROM match_violations
UNION ALL
SELECT * FROM core_violations
```

**Note**: The test uses hardcoded rates (4% match cap, 2% core) for the validation. A more robust test would dynamically retrieve the configured rates, but this is sufficient for the current plan design scope.

**Alternatives Considered**:
- Schema test on column: Doesn't support cross-table validation
- Generic test macro: Overkill for single use case

---

## Summary

All research questions resolved. No NEEDS CLARIFICATION items remain.

| Topic | Decision | Confidence |
|-------|----------|------------|
| IRS Limits | CSV seed column with published + projected values | High |
| Match Integration | CTE + LEAST() at match cap line | High |
| Core Integration | CTE + LEAST() at core calculation line | High |
| Proration | Apply limit to already-prorated amounts | High |
| Audit Trail | Boolean `irs_401a17_limit_applied` field | High |
| Test Pattern | Singular dbt test returning violations | High |
