# Compliance reporting

In Studio, open **NDT & Compliance**, choose **Compliance Overview**, select a
completed scenario and year, then run the report. Comparison mode supports up to
six scenarios. Click a limit-status count or catch-up heading to inspect a
paginated employee population. ADP, ACP, and 415 links open the existing test
views; run the selected test to see its full details and options.

Reports read the selected successful run without updating its IRS seed or other
archived data. The overview identifies the run and recorded limits, marks
estimated years, and warns when limit values differ from the current seed.
The separate dbt `dq_compliance_monitoring` model remains disabled. Its UNION
columns now align and it compiles and runs against an isolated 2025–2027 run,
but its administrative branch still treats the source's `NORMAL` and
`IRS_LIMITED` quality flags as violations because it expects `VALID`. Its
compensation branch also calls above-cap pay a violation rather than a review
population. Re-enable it only after those reporting semantics are corrected.
Updated seed values apply to new simulations; rerun a scenario to adopt them.
NDT tests also use read-only connections and never repair missing or outdated
seed tables in an archive. Simulation initialization loads the required seeds;
rerun a legacy scenario if its NDT test reports missing tables or columns.
The 2026 seed uses the [published IRS limits](https://www.irs.gov/retirement-plans/cola-increases-for-dollar-limitations-on-benefits-and-contributions).
For 2027–2035, the seed holds ordinary catch-up capacity at $8,000 and super
catch-up capacity at $11,250 above each year's projected base limit. This is a
conservative projection, not an indexed catch-up forecast. Actual future IRS
limits may be higher; replace estimated seed rows when published limits become
available and rerun scenarios to adopt them.
Employee details reject changed result evidence with HTTP 409, requiring an
overview refresh. Missing limits or required inputs are unavailable, not zero.

## Metrics and assumptions

- **402(g):** annual employee deferrals divided by the simulation-age-appropriate
  total limit, including ordinary or super catch-up where applicable.
- **415(c):** the existing NDT annual-additions calculation: employee deferrals
  excluding modeled age-eligible catch-up up to its allowance, plus employer match and core. The
  applicable limit is the smaller of the annual dollar limit and the existing
  annualized-compensation proxy. Forfeitures and employee after-tax additions
  are not included in this preview.
- **401(a)(17):** actual prorated annual compensation compared with the annual
  compensation cap. Compensation above the cap is contribution-basis impact,
  not itself a violation. A mid-year hire does not prorate the annual dollar cap;
  short plan years require separate treatment not modeled here.
- **Catch-up:** disjoint ordinary and super age groups from the recorded seed.
  Capacity is the age-specific total deferral limit minus the base limit.
  Modeled use is deferrals above the base limit, bounded by catch-up capacity.
  Remaining capacity is capacity minus modeled use. Utilization is reported
  over employees with available contribution inputs; coverage counts are shown.
  These projections use simulation age, not a new determination from birth dates,
  and do not model catch-up triggered by other plan/test limits or Roth catch-up
  eligibility.
- **NDT:** reuses ADP current-year testing without a safe-harbor election, ACP,
  and 415. Open the existing ADP view to apply alternate testing assumptions.
  These remain modeled test previews subject to their existing coverage.

Statuses are mutually exclusive: below threshold, near limit (default 95%), at
limit, over limit, or unavailable. Dollar boundaries are rounded to cents.
Headroom is signed; excess is nonnegative. Empty catch-up denominators return
null utilization. Reporting populations match the existing 415 eligibility
predicate, including legacy rows with unspecified eligibility. No active-only
filter is applied, so terminated employees' annual contributions are retained.
Legacy archives without plan-design identity remain readable with that field
explicitly unavailable. No names or SSNs are returned.

## API

`GET /api/workspaces/{workspace_id}/analytics/ndt/compliance`
accepts `scenarios`, `year`, and optional `warning_threshold`.

`GET /api/workspaces/{workspace_id}/analytics/ndt/compliance/employees`
accepts `scenario_id`, `year`, the summary's `evidence`, `metric` (`402g`, `415c`,
`401a17`, `catch_up`, or `super_catch_up`), optional `limit_status`,
`warning_threshold`, `offset`, and `limit` (default 50, maximum 200).

## Validation

```bash
source .venv/bin/activate
pytest tests/unit/api/test_compliance_service.py tests/test_ndt_415.py tests/unit/config/test_irs_limits_seed.py -q
pytest tests/integration/test_compliance_reporting.py -q
cd planalign_studio
npm run typecheck
npm run test -- components/ComplianceOverview.test.tsx
```

The integration check builds a synthetic 2025–2027 simulation in pytest's
temporary directory; it never writes to `dbt/simulation.duckdb`.

### ADP uniform QNEC planning estimate

A failing current-year ADP test includes a modeled uniform QNEC estimate for all
included NHCEs, including nondeferrers. It applies a uniform percentage of capped
testing compensation, rounds each participant's principal up to the cent, and
recomputes the ADP test. The estimate reports recipients, total principal, and
before/after NHCE averages. Amounts that exceed the modeled 415 annual additions
limit are flagged as infeasible and are not clipped. Unavailable limits are
explicitly disclosed; prior-year testing is unsupported.

This is a planning estimate only and requires plan administrator review before
any correction. It excludes earnings and uses compensation-based HCE classification.
The retained `excess_hce_amount` field is an aggregate modeled estimate
((HCE average − threshold) × total HCE testing compensation), not a participant-level
refund calculation.
