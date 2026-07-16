# Data Model: Employee Event Timeline

**Feature**: 114-employee-event-timeline | **Date**: 2026-07-15

No database schema changes. All entities below are Pydantic v2 API models (`planalign_api/models/timeline.py`) projected from existing marts, plus their TypeScript mirrors in `planalign_studio/services/api.ts`.

## Source tables (read-only, existing)

| Table | Role | Key columns used |
|-------|------|------------------|
| `fct_yearly_events` | Primary event history | `event_id`, `employee_id`, `event_type`, `simulation_year`, `effective_date`, `event_sequence`, `event_details`, `compensation_amount`, `previous_compensation`, `employee_deferral_rate`, `prev_employee_deferral_rate`, `level_id` |
| `fct_employer_match_events` | Match contribution events (merged into timeline) | `event_id`, `employee_id`, `event_type`, `simulation_year`, `effective_date`, `amount`, `employee_deferral_rate`, `event_payload` |
| `fct_workforce_snapshot` | Per-year state strip; autocomplete & filter population | identity (`employee_id`, `employee_ssn`, `employee_birth_date`, `employee_hire_date`), demographics (`current_age`, `current_tenure`, `level_id`, bands), status (`employment_status`, `detailed_status_code`, `termination_date`), plan state (`current_eligibility_status`, `is_enrolled_flag`, `employee_enrollment_date`, `current_deferral_rate`, `participation_status`, `total_deferral_escalations`, `has_deferral_escalations`), money (`current_compensation`, `prorated_annual_compensation`, `ytd_contributions`, `pre_tax_contributions`, `roth_contributions`, `employer_match_amount`, `employer_core_amount`, `total_employer_contributions`, `irs_limit_reached`), `simulation_year` |

## API models

### TimelineEvent

One entry in the merged timeline. Discriminating field: `source`.

| Field | Type | Notes |
|-------|------|-------|
| `event_id` | `str` | UUID from source table |
| `source` | `Literal["yearly", "employer_match"]` | Which store it came from |
| `event_type` | `str` | Passed through as stored (e.g., `hire`, `deferral_escalation`, match event type); never filtered to a known list (FR-002: future types flow through) |
| `simulation_year` | `int` | |
| `effective_date` | `date` | |
| `event_details` | `str \| None` | Human-readable detail string as stored |
| `compensation_amount` | `float \| None` | Hire/raise/promotion comp; match `amount` maps here for uniform display |
| `previous_compensation` | `float \| None` | |
| `deferral_rate` | `float \| None` | `employee_deferral_rate` |
| `prev_deferral_rate` | `float \| None` | |
| `level_id` | `int \| None` | |

**Ordering rule (FR-005)**: `(simulation_year, effective_date, COALESCE(event_sequence, 999), event_id)` — applied in SQL, asserted in tests.

### YearState

The state strip for one simulation year (projection of one `fct_workforce_snapshot` row). Nullable throughout — a year can have events but no snapshot row and vice versa (FR-008).

| Field | Type |
|-------|------|
| `simulation_year` | `int` |
| `employment_status` | `str \| None` |
| `detailed_status_code` | `str \| None` |
| `current_compensation` | `float \| None` |
| `prorated_annual_compensation` | `float \| None` |
| `level_id` | `int \| None` |
| `current_age` | `int \| None` |
| `current_tenure` | `float \| None` |
| `eligibility_status` | `str \| None` |
| `is_enrolled` | `bool \| None` |
| `enrollment_date` | `date \| None` |
| `current_deferral_rate` | `float \| None` |
| `participation_status` | `str \| None` |
| `total_deferral_escalations` | `int \| None` |
| `ytd_contributions` | `float \| None` |
| `pre_tax_contributions` | `float \| None` |
| `roth_contributions` | `float \| None` |
| `employer_match_amount` | `float \| None` |
| `employer_core_amount` | `float \| None` |
| `total_employer_contributions` | `float \| None` |
| `irs_limit_reached` | `bool \| None` |

### TimelineYear

One page unit (FR-006): a year's events + that year's state.

| Field | Type |
|-------|------|
| `simulation_year` | `int` |
| `events` | `list[TimelineEvent]` |
| `state` | `YearState \| None` |

### EmployeeTimelineResponse

| Field | Type | Notes |
|-------|------|-------|
| `workspace_id` / `scenario_id` / `employee_id` | `str` | Echo of the request (employee_id normalized) |
| `employee` | `EmployeeIdentity \| None` | `None` ⇒ FR-009 "no records found" state |
| `available_years` | `list[int]` | Every year with events **or** a snapshot row, ascending |
| `years` | `list[TimelineYear]` | The requested page of years, oldest-first |
| `start_year` / `years_requested` | `int` | Pagination echo |

### EmployeeIdentity

Header block for the page. Includes identity fields per Clarification Q1 (SSN as stored — masked upstream; birth date shown).

| Field | Type |
|-------|------|
| `employee_id` | `str` |
| `employee_ssn` | `str \| None` |
| `employee_birth_date` | `date \| None` |
| `employee_hire_date` | `date \| None` |

### EmployeeSearchResult / EmployeeSearchResponse (autocomplete + filter list)

`EmployeeSearchResult` — one row of the discovery list (FR-014's identifying columns):

| Field | Type |
|-------|------|
| `employee_id` | `str` |
| `employment_status` | `str \| None` |
| `level_id` | `int \| None` |
| `current_compensation` | `float \| None` |
| `simulation_year` | `int` | Year the row's state is from |

`EmployeeSearchResponse`: `results: list[EmployeeSearchResult]`, `total: int`, `page: int`, `page_size: int`.

### Filter parameters (query params, FR-013)

| Param | Type | Maps to |
|-------|------|---------|
| `q` | `str \| None` | `employee_id` prefix (trimmed, case-insensitive) — autocomplete mode |
| `status` | `str \| None` | `employment_status` |
| `level` | `int \| None` | `level_id` |
| `year` | `int \| None` | `simulation_year` (defaults to latest year in DB) |
| `enrolled` | `bool \| None` | `is_enrolled_flag` |
| `has_escalations` | `bool \| None` | `has_deferral_escalations` |
| `page`, `page_size` | `int` | LIMIT/OFFSET (page_size ≤ 200) |

## Comparison (US5) — no new server model

The frontend requests `EmployeeTimelineResponse` once per scenario and renders two `TimelineColumn`s. Client-side composition rules:

- **Year alignment**: union of both `available_years`, ascending; a year missing from one response renders as "not simulated in this scenario" in that column (edge: mismatched year ranges).
- **Absent employee**: `employee == null` in one response renders FR-009's message in that column only (US5 scenario 3).
- **Same-scenario guard**: the compare picker excludes the current scenario (edge: comparing with itself).

## State transitions

None — the feature is stateless and read-only. The only client state is the route (`workspaceId`, `scenarioId`, `employeeId`, `?compare=`), which fully determines the view (FR-011/FR-017 deep-link contract).
