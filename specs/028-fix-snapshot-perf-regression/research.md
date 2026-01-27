# Research: Fix Workforce Snapshot Performance Regression

**Feature**: 028-fix-snapshot-perf-regression
**Date**: 2026-01-27

## Phase 0 Research Summary

### Research Task 1: Scalar Subquery Performance in DuckDB

**Question**: Does DuckDB optimize correlated scalar subqueries?

**Finding**: No - DuckDB (like most OLAP databases) does not automatically decorrelate scalar subqueries that reference outer query columns. Each scalar subquery executes once per row in the outer query, resulting in O(n²) complexity for n employees.

**Evidence**: The current implementation (lines 971-1025) contains 4 scalar subqueries that each:
1. Reference `final_workforce_with_contributions.employee_id` (outer column)
2. Scan `int_baseline_workforce` table
3. Execute `LIMIT 1` to return a single boolean

For 100K employees, this creates 400K subquery executions per year.

**Decision**: Replace with single JOIN + CASE expression
**Rationale**: JOINs are hash-based O(n) operations; CASE expressions are O(1) per row
**Alternatives Rejected**:
- Window functions: Not applicable since baseline is a separate table
- Materialized view: Adds operational complexity without solving root cause
- DuckDB hints: No optimizer hints available for this pattern

---

### Research Task 2: Missing simulation_year Filter Impact

**Question**: What is the performance impact of missing simulation_year filters?

**Finding**: Three locations read full historical data instead of current year only:

| Location | Current Behavior | Row Impact (5-year sim) |
|----------|-----------------|------------------------|
| Line 373 | Reads all years from int_baseline_workforce | 5x table scan |
| Line 423 | NOT IN subquery reads all years | 5x subquery execution |
| Line 472 | Baseline fallback reads all years | 5x unnecessary I/O |

**Decision**: Add `WHERE simulation_year = {{ var('simulation_year') }}` to all three locations
**Rationale**: Reduces I/O proportionally to simulation span
**Alternatives Rejected**:
- Incremental model changes: Already incremental; filter is the issue
- Table partitioning: DuckDB doesn't support physical partitions

---

### Research Task 3: DuckDB Best Practices for Anti-Pattern Replacement

**Question**: What is the optimal pattern for replacing scalar subqueries with JOINs?

**Finding**: DuckDB documentation and community best practices recommend:
1. Create a CTE that pre-filters the lookup table to the exact rows needed
2. LEFT JOIN the CTE once to the main query
3. Use CASE expression on the joined column for conditional logic

**Decision**: Implement `baseline_comp_for_quality` CTE pattern
```sql
baseline_comp_for_quality AS (
    SELECT employee_id, current_compensation AS baseline_compensation
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year') }}
)
```

**Rationale**:
- Single table scan of int_baseline_workforce
- Hash join is O(n) for both tables
- CASE expression evaluates all thresholds in single pass

---

### Research Task 4: Edge Case Handling

**Question**: How to handle zero/null baseline compensation and new hires?

**Finding**: Current scalar subqueries already guard against division by zero with `b.current_compensation > 0`. The LEFT JOIN pattern must preserve this behavior.

**Decision**: Use conditional CASE with explicit null/zero checks:
```sql
CASE
    WHEN bcq.baseline_compensation IS NULL THEN 'NORMAL'  -- New hire
    WHEN bcq.baseline_compensation <= 0 THEN 'NORMAL'     -- Zero baseline
    WHEN (current_compensation / bcq.baseline_compensation) > 100.0 THEN 'CRITICAL_INFLATION_100X'
    ...
END
```

**Rationale**: Matches existing behavior exactly; new hires have no baseline row so LEFT JOIN returns NULL

---

## All NEEDS CLARIFICATION Resolved

No outstanding unknowns. All technical decisions documented above.
