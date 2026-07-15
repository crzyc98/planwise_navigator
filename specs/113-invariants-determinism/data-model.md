# Data Model: Multi-Year Invariant Suite + Determinism Test

This feature creates no new production tables. Its data artifacts are test fixtures and in-test structures; the simulation tables it *reads* are listed for reference.

## New Fixture Data

### Reference census (`tests/fixtures/invariant_census.csv`)

One row per employee, ~150 rows, deterministic and checked in. Columns must satisfy the `stg_census_data.sql` schema scaffold (superset ignored, missing columns nulled by the scaffold):

| Field | Type | Constraints / design rules |
|---|---|---|
| employee_id | VARCHAR | Unique; stable format `INV_EMP_####` |
| employee_ssn | VARCHAR | Synthetic, obviously fake range |
| employee_birth_date | DATE | Chosen so every age band (0-25, 25-35, 35-45, 45-55, 55-65, 65+) is populated at 2025 |
| employee_hire_date | DATE | Every tenure band (0-2, 2-5, 5-10, 10-20, 20+) populated; includes hires straddling the auto-enrollment hire-date cutoff |
| employee_termination_date | DATE | NULL for actives; ≥1 pre-simulation terminated employee |
| employee_gross_compensation | DECIMAL(12,2) | Spans all job levels' comp bands (drives level assignment) |
| employee_capped_compensation | DECIMAL(12,2) | ≤ gross; respects 401(a)(17) for the base year |
| active | BOOLEAN | Consistent with termination_date |
| employee_deferral_rate | DECIMAL(7,5) | >0 for enrolled-at-census subset; NULL/0 for never-enrolled |
| employee_contribution / pre_tax / roth / after_tax | DECIMAL(12,2) | Consistent with deferral rate × comp for enrolled subset |
| employer_core_contribution / employer_match_contribution | DECIMAL(12,2) | Present for enrolled subset |
| eligibility_entry_date | DATE | Set for eligible subset |
| scheduled_hours_per_week | DECIMAL(5,2) | Mostly 40; a few part-time rows |
| auto_escalation_opt_out | BOOLEAN | Mostly false; ≥2 true (exercises escalation suppression) |
| eligibility_override | BOOLEAN | Mostly NULL/false |

**Coverage assertions** (enforced by a fixture self-test so census edits can't silently lose coverage):
- every age band ≥ 5 employees; every tenure band ≥ 5; every job level ≥ 3
- enrolled-at-census ≥ 30; never-enrolled ≥ 30
- ≥ 5 hires on each side of the auto-enrollment cutoff

### Fixed configuration (`tests/fixtures/invariant_config.yaml`)

Pydantic-validated `SimulationConfig` source. Pinned values: years 2025–2027; `random_seed` fixed; auto-enrollment on with mid-census `hire_date_cutoff`; auto-escalation on with a cap low enough to bind by 2027; multi-tier match; positive `target_growth_rate`; `census_parquet_path` injected at runtime by the fixture (tmp parquet path).

## Test-Side Structures

### `Invariant` (dataclass, `tests/invariants/catalog.py`)

| Field | Type | Notes |
|---|---|---|
| name | str | Unique slug, e.g. `enrollment-coherence-no-duplicate-enrollment` |
| description | str | One sentence, rendered in failure output |
| guarded_issue | str \| None | e.g. `#418`; rendered in failure output |
| violation_sql | str | Query over the built DB returning violating rows (empty ⇒ pass); first columns MUST be `employee_id`, `simulation_year` where applicable (FR-011) |
| sample_limit | int = 20 | Bound on rendered violating rows |

**Registry**: module-level tuple; parametrized into pytest via `@pytest.mark.parametrize("invariant", CATALOG, ids=lambda i: i.name)`.

### `ExemptField` (`tests/invariants/comparison.py`)

| Field | Type | Notes |
|---|---|---|
| table | str | `fct_yearly_events` \| `fct_workforce_snapshot` |
| column | str | e.g. `created_at` |
| justification | str | Required non-empty (FR-010); rendered in suite docs |

Whole-table exclusions (e.g. `run_metadata`) documented alongside with the same justification rule.

### Determinism comparison result

Per compared table: `(row_count_a, row_count_b, diff_row_count, sample_rows)` — failure message includes table name, counts, and ≤20 canonical-ordered differing rows (FR-011, acceptance scenario 2.3).

## Simulation Tables Read (existing, unchanged)

- `fct_yearly_events` — event uniqueness, enrollment coherence, event/snapshot consistency, deferral coherence, determinism diff
- `fct_workforce_snapshot` — continuity, event/snapshot consistency, growth exactness, determinism diff
- `int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator` — cross-checked against events for coherence invariants
- `run_metadata` — excluded from determinism diff; optionally asserted to contain exactly one fingerprint per run (config-drift sanity)

## State Transitions Verified (the invariant families)

1. **Event uniqueness**: `event_id` unique across all years (FR-003).
2. **Enrollment coherence**: enrollment events per employee alternate enrollment ↔ opt-out; census-enrolled stay enrolled absent an explaining event across all 3 years (FR-004, #418).
3. **Year-over-year continuity**: ending actives(Y) = starting actives(Y+1); no active-after-termination without rehire (FR-005).
4. **Event/snapshot consistency**: every snapshot row's status/enrollment/deferral is explained by the event stream; no rows from outside the run's years/config (FR-006, #419).
5. **Growth exactness**: per-year headcount matches the E077 solver's documented rounding rule exactly (FR-007).
6. **Deferral coherence**: rate changes ⇔ explaining events; escalated rate ≤ cap; opt-out employees never escalated (FR-008).
