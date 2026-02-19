# Research: NDT ACP Testing

**Branch**: `050-ndt-acp-testing` | **Date**: 2026-02-19

## R1: ACP Formula — IRS Standard Definition

**Decision**: Use standard IRS ACP formula per Treas. Reg. 1.401(m)-2: `ACP = (employer matching contributions + employee after-tax contributions) / eligible compensation`. Elective deferrals excluded (reserved for future ADP test).

**Rationale**: Ensures compliance-accurate results. The simulation currently does not model after-tax contributions, so MVP ACP = `employer_match_amount / eligible_compensation`.

**Alternatives considered**:
- Combined ACP+ADP formula (rejected: conflates two distinct IRS tests)
- Elective deferral-inclusive ACP (rejected: not IRS-standard)

## R2: Eligible Test Population

**Decision**: Include all plan-eligible employees regardless of enrollment status. Non-participants have 0% ACP.

**Rationale**: IRS rules require all eligible employees in the test population. Excluding non-participants overstates group averages.

**Data source**: `fct_workforce_snapshot.current_eligibility_status = 'eligible'` identifies plan-eligible employees. `is_enrolled_flag` distinguishes participants from non-participants.

## R3: Alternative Test Formula

**Decision**: Full IRS formula — alternative test threshold = lesser of (NHCE ACP x 2) and (NHCE ACP + 2 percentage points).

**Rationale**: The simplified "NHCE + 2%" version produces false passes when NHCE ACP is low (e.g., NHCE ACP = 1% → simplified threshold = 3%, correct threshold = 2%).

**Alternatives considered**:
- Simplified NHCE + 2% (rejected: produces incorrect results at low ACP levels)

## R4: HCE Compensation Threshold — Seed Data

**Decision**: Add `hce_compensation_threshold` column to existing `config_irs_limits.csv`.

**Rationale**: The seed already contains year-indexed IRS limits (402(g), 401(a)(17)). Adding the HCE threshold column keeps all IRS limits in one place.

**Values**: 2024: $155,000; 2025: $160,000; 2026: $165,000 (projected); continuing with ~$5K annual escalation through 2035.

**Current seed columns**: `limit_year, base_limit, catch_up_limit, catch_up_age_threshold, compensation_limit`. New column appended: `hce_compensation_threshold`.

## R5: Data Availability in fct_workforce_snapshot

**Decision**: All required data for ACP calculation is available in `fct_workforce_snapshot`.

**Key columns mapped to ACP needs**:
| ACP Input | Snapshot Column | Notes |
|-----------|----------------|-------|
| Eligible compensation | `prorated_annual_compensation` | 401(a)(17) capped upstream |
| Employer match | `employer_match_amount` | From `int_employee_match_calculations` |
| Employer core | `employer_core_amount` | Non-elective contribution |
| Eligibility status | `current_eligibility_status` | `eligible` or `pending` |
| Enrollment flag | `is_enrolled_flag` | Boolean |
| Employment status | `employment_status` | `active` or `terminated` |
| Prior-year compensation | `current_compensation` at `simulation_year - 1` | For HCE determination |

**Gap identified**: No `after_tax_contributions` column exists. MVP uses `employer_match_amount` only. Future: add after-tax contribution modeling.

## R6: No Existing HCE Models

**Decision**: Build HCE determination as a new read-only analytics query (not a dbt intermediate model).

**Rationale**: HCE determination for NDT is a post-simulation analytics operation. It reads from `fct_workforce_snapshot` (a marts-layer table), which means a dbt intermediate model would create a circular dependency (int → fct is prohibited by constitution). Instead, the HCE classification and ACP computation will be performed in the API service layer as DuckDB analytical queries against the completed simulation database.

**Alternatives considered**:
- dbt intermediate model `int_hce_determination.sql` (rejected: would need to read `fct_workforce_snapshot`, violating the `int → fct` dependency prohibition)
- dbt analysis model (considered: viable but adds dbt build complexity for a read-only analytics feature)

## R7: API Pattern — Multi-Scenario Analytics

**Decision**: Follow the `analytics.py` DC plan comparison pattern: `GET /api/workspaces/{workspace_id}/analytics/ndt/acp?scenarios=id1,id2&year=2025`.

**Rationale**: Consistent with existing multi-scenario endpoint patterns. Single query parameter for scenario selection, explicit year parameter.

**Key patterns to follow**:
- Router: dependency injection via `get_settings()` → `WorkspaceStorage` → `NDTService`
- Validation: workspace exists → scenarios exist → scenarios completed
- DB access: `DatabasePathResolver.resolve()` → `duckdb.connect(read_only=True)`
- Response: Pydantic model with per-scenario results

## R8: Frontend Pattern — Analytics Page

**Decision**: Follow `DCPlanAnalytics.tsx` pattern with scenario multi-select + year dropdown.

**Rationale**: Most natural fit — the NDT page needs workspace context, scenario selection, year selection, and a "Run Test" action button.

**Key patterns to follow**:
- `useOutletContext<LayoutContextType>()` for active workspace
- Cascading effects: workspace → scenarios → available years
- Scenario pills with toggle handler and `MAX_SCENARIO_SELECTION` cap
- Explicit "Run Test" button (not auto-fetch) since test is a deliberate action
- Loading → error → empty → results conditional rendering
- Nav item: `<NavItem to="/analytics/ndt" icon={<Shield size={20} />} label="NDT Testing" />`
