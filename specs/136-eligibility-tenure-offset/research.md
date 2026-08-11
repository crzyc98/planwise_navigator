# Research: Correct Employer Contribution Eligibility Service Credit

## Decision: Treat the current-year workforce accumulator as the only service authority

**Rationale**: `int_workforce_state_accumulator` already carries the accepted per-employee annual workforce state and feeds eligibility, contributions, and the final snapshot in the sanctioned pipeline order. Its `current_tenure` is advanced once for continuing active employees, set to zero for current-year hires, and recomputed through the termination date for employees terminating during the year. The defect is downstream reconstruction: eligibility replaces this value with `prior_workforce.current_tenure + 2` after the opening year.

**Alternatives considered**:

- Recalculate service from hire date in each benefit model — rejected because it duplicates workforce-state policy and allows the models to drift again.
- Read `fct_workforce_snapshot.current_tenure` — rejected because a current-year `int_*` to `fct_*` dependency would violate the build order and create a circular dependency.
- Increment prior-year tenure in eligibility — rejected because the accumulator has already performed that transition and has applied current-year termination events.

## Decision: Use termination-date service for mid-year terminations

**Rationale**: The authoritative accumulator calls `calculate_tenure` with the employee's termination date, and the macro documents that service stops on that date. FR-001 and FR-004 require eligibility and its audit value to match that workforce record. Existing `allow_terminated_new_hires` and `allow_experienced_terminations` settings decide whether termination status may bypass the status gate; they do not authorize invented service credit.

**Alternatives considered**:

- Credit service through December 31 — rejected because it conflicts with the authoritative workforce record and could give an employee service they did not work.
- Preserve the core/match `prior + 1` experienced-termination adjustment — rejected because it produces two service values for one employee-year and violates FR-006.

## Decision: Align service-dependent rate selection with the corrected eligibility basis

**Rationale**: FR-006 explicitly requires a single service basis across the eligibility gate and any service-graded contribution rate. Core `graded_by_service` and `points_based`, plus match `graded_by_service`, `tenure_graded`, and `points_based`, all depend on completed service. Their audit field must therefore equal the eligibility/workforce value even when an explicit exception lets an employee pass the eligibility gate.

**Alternatives considered**:

- Fix only the eligibility gate — rejected because it leaves a documented inconsistency and could gate an employee at one service level while pricing the contribution at another.
- Align core rates but not match rates — rejected because core and match would remain irreconcilable under identical requirements.
- Change age-banded or flat rates — rejected because those modes do not use service and are outside the affected logic.

## Decision: Preserve existing exception semantics and configuration contracts

**Rationale**: The issue concerns the value compared with a waiting period, not the configured rules. New-hire and termination allowances remain explicit bypasses, and match backward-compatibility mode continues to use its existing active-plus-hours behavior when `apply_eligibility` is false. No setting is renamed or added, satisfying FR-003 and FR-009.

**Alternatives considered**:

- Remove service exceptions — rejected as an unrelated plan-design behavior change.
- Force match eligibility enforcement on — rejected because it would break the documented backward-compatibility contract.

## Decision: Enforce exact equality with layered tests

**Rationale**: A singular dbt test can be run against the current build-year materialization and fails CI/dbt validation on any workforce/eligibility divergence. Existing core audit coverage already expects exact equality, while the service-match boundary test currently tolerates a one-year difference; changing that comparison to exact equality makes the reported defect fail. Fast synthetic query tests prove the invariant detects a deliberately reintroduced offset. A separate isolated five-year pytest suite proves the cross-year cost and eligibility outcomes that a single dbt invocation cannot retain.

**Alternatives considered**:

- Integration tests only — rejected because they diagnose the defect late and may not identify which consumer drifted.
- dbt tests only — rejected because current-year intermediate tables do not retain a complete multi-year comparison between waiting-period configurations.
- Add an eighth case to the Feature 124 edge matrix — rejected because that catalog is intentionally capped at seven cases for its twenty-minute CI budget; this feature needs several related scenario runs with distinct assertions.

## Decision: Correct only new runs; do not migrate saved results

**Rationale**: Saved scenario databases are auditable run artifacts tied to their original code/configuration provenance. Mutating them would violate reproducibility and event-sourcing expectations. Analysts obtain corrected figures by rerunning affected plan designs.

**Alternatives considered**:

- Rewrite historical DuckDB outputs — rejected because it would destroy the association between recorded run provenance and its produced results.
- Add a compatibility flag for the faulty basis — rejected because the incorrect calculation is not a supported plan-design behavior.

## Decision: Keep adjacent age and reporting-band inconsistencies out of scope

**Rationale**: The employee-contribution path contains separate later-year age arithmetic used by points-based match calculations, and the workforce accumulator's reported `tenure_band` can diverge from its termination-date `current_tenure`. Neither issue causes the employer eligibility service offset described by this feature. Changing them here would broaden the behavioral blast radius beyond the stated core/match service basis.

**Alternatives considered**:

- Correct all age/tenure consumers in one patch — rejected because those consumers govern different business decisions and need their own characterization and requirements.
- Silently reuse a downstream age or tenure-band value as the eligibility source — rejected because it would replace one duplicated policy with another.
