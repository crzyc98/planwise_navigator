# Contribution-source reporting

Source amounts are **modeled allocations, not payroll or tax-compliance results**.
The default `legacy_estimate` policy preserves the historical 85% pre-tax / 15%
Roth assumption, now labeled on every snapshot row and in the employee timeline.
New allocations round Roth to cents and calculate pre-tax as the rounded total
minus Roth. Source allocation itself does not change total deferrals, immutable
events, employer match, annual-additions calculations or enrollment behavior.
Contribution caps now use calendar-year-end age rather than the workforce's
prior-year age, correcting catch-up boundary years (50, 60 and 64). This can
change total deferrals and downstream match in those years.

## Policy and evidence

The top-level simulation/workspace YAML block is validated by Pydantic and
exported to dbt. Use `assumed_split` to choose another ordinary Roth share.
This is a scenario-wide assumed election, not an employee election inferred from
the optional census `roth_contribution` amount. Historical census amounts do not
establish future elections or qualifying current-year Roth deferrals.

```yaml
contribution_sources:
  policy: assumed_split
  roth_fraction: 0.15
  roth_available: true
  mandatory_roth_enabled: true
  applicability: single_employer_401k
  employer_id: sponsor_a
  wage_evidence:
    - employee_id: SYNTHETIC_001
      employer_id: sponsor_a
      wage_year: 2025
      wages: 150001.00
      basis: confirmed
      provenance: synthetic_example
  projected_thresholds:
    - year: 2027
      threshold: 155000
      provenance: analyst_assumption_not_published_guidance
```

Wages must be the sponsoring employer's prior-calendar-year section 3121(a)
wages. Each employee/employer/year key is unique. `confirmed` and `forecast`
are distinct evidence bases; both require provenance. Zero is a known zero;
an absent record is unavailable evidence. First-year employees, new hires and
later simulation years use exactly the same lookup. Neither current salary,
prior simulated compensation, hire dates nor the Social Security wage base
substitutes for evidence. Supply subsequent-year records explicitly; forecasts
remain assumptions. Treat these YAML records and compiled dbt artifacts as
sensitive employee data and keep them out of version control.

The snapshot stores the effective policy, fraction, version, matched wage amount,
employer, wage year, evidence basis/provenance, year-end age, threshold and its
basis/provenance, rule version, required catch-up and additional Roth reallocation.
This evidence travels with the archived database. Reading old archives does not
recalculate amounts using today's configuration. Archives lacking these columns
are labeled `legacy_unverified` in the API, with no inferred wage evidence.

## Scoped mandatory Roth model

Opt-in applicability covers a single-employer, ordinary 401(k), without special
governmental or collectively bargained transition treatment. Other plan types,
employer aggregation and special transitions must use `unsupported` applicability.
The default is `mandatory_roth_enabled: false` / `not_evaluated`.

For 2026 the rule uses prior-year wages **strictly greater than $150,000**.
The version is `sec603_2026_good_faith_v1`; later years use
`sec603_2027_v1`. The statutory start in 2026 is distinct from general final-rule
applicability in 2027. Future wage thresholds require an explicit projection;
missing thresholds produce `unresolved_threshold`. They are not extrapolated
silently. The existing IRS seed supplies published/projected base, ordinary and
ages-60–63 limits. Year-end age is derived from birth year; missing birth dates
produce `unresolved_age` when catch-up is used.

Only **deferrals exceeding the base elective-deferral dollar limit** are treated
as catch-up. Plan-limit and ADP-triggered catch-up remain unsupported, including
corrective-distribution classification tracked by #842. `no_base_limit_catch_up`
does not assert that no other statutory catch-up trigger exists.

For an affected employee, final modeled Roth is the greater of the assumed Roth
allocation and actual modeled base-limit catch-up usage. This credits Roth
already allocated during the year instead of adding catch-up twice. For example,
$30,000 total in 2026 at a 15% Roth preference starts with $4,500 Roth; $5,500
catch-up requires only $1,000 additional reallocation. At 50% Roth, no additional
reallocation is needed.

`required` means the scoped model used confirmed wages and the published 2026
threshold. Forecast wages or projected thresholds produce
`required_under_assumptions`. Neither is a full compliance determination.
Missing evidence retains the assumed split with an explicit unresolved status
and a null required amount; it is not treated as an exemption.

A no-Roth plan requires `policy: assumed_split`, `roth_fraction: 0`, and
`roth_available: false`. If catch-up requires Roth, `blocked_no_roth` exposes
the required amount but sets both source amounts to null. The model does not
silently reduce employee deferrals or downstream match. This is an unresolved
plan restriction, not an executable payroll allocation. Age-ineligible or
over-limit modeled catch-up similarly blocks allocation. Resolve those conditions
before relying on source amounts.

## Validation and references

```bash
source .venv/bin/activate
pytest tests/unit/config/test_contribution_sources.py tests/test_timeline_service.py -q
pytest tests/integration/test_contribution_source_pipeline.py -q
```

The integration test creates synthetic census data, an isolated database and
separate dbt target/log paths for a full 2025–2027 pipeline run. It never writes
`dbt/simulation.duckdb`. The dbt reconciliation test checks supported source sums,
blocked nulls and required Roth coverage.

Authority checked October 17, 2026:
[IRS catch-up overview](https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-catch-up-contributions),
[Notice 2025-67](https://www.irs.gov/irb/2025-49_IRB), and
[final regulations](https://www.irs.gov/irb/2025-40_IRB).
Personal taxes, withholding, payroll execution, retirement balances and optional
behavioral contribution reductions are outside this model.
