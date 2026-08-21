# Net Employer Cost (issue #444)

A plan sponsor's question is "what does this design cost me per year, **net of
forfeitures**?" The Cost Comparison page used to answer only the gross half of
it. This feature adds gross cost, forfeiture offset and net cost to the page the
user is already on, and to `planalign analyze cost` and the Excel export, from
one shared function.

## The correction underneath it

Forfeiture used to be scored against the **prior year's** employer
contributions — one year of match plus core. That is a single year's funding,
not an account balance, so an employee on a 3-year cliff who terminated in year
three was scored as forfeiting one year of employer money when a sponsor would
forfeit all three.

The basis is now the employee's **cumulative** employer contributions across
every simulation year before the year they terminated. On the reference dev
database this moves 2029 forfeitures from ~$5.1M to ~$14.8M. The Vesting
screens (`VestingAnalysis`, `ForfeitureProjection`) pick the corrected figure up
automatically — their numbers move materially, which is the point.

**Limitation, stated everywhere it is used:** contributions made *before* the
first simulation year are outside the run and are not in the basis. Forfeitures
for employees hired before the horizon are understated.

## Forfeiture policy

Policy decides whether the sponsor's outlay actually falls. These are not three
flavours of the same subtraction:

| Policy | Effect on net employer cost |
|---|---|
| `offset_employer_contributions` | Offset applies — reduces sponsor outlay |
| `pay_plan_expenses` | Offset applies — reduces sponsor outlay |
| `reallocate_to_participants` | **Offset is $0** — the money goes to remaining participants' accounts and the sponsor still funds the full match |

Under reallocation the forfeiture is still disclosed, as a participant-side
allocation, alongside a $0 employer offset.

## Timing

Forfeitures from year N terminations are recognized and applied against **year
N+1** employer cost.

A year with no measurable source is rendered gross-only and flagged — **never a
$0 offset**. Two years are unmeasurable in every run:

- the first simulation year, which has no prior plan year at all;
- the second, whose source terminations accrued their employer money before the
  horizon (`has_prior_year_basis: false`).

Horizon totals include those years' gross cost unchanged, and list them in
`years_without_offset_basis`.

## Where the one definition lives

`planalign_api/services/employer_cost_service.py`:

- `GROSS_MATCH_SQL` / `GROSS_CORE_SQL` / `GROSS_EMPLOYER_COST_SQL` /
  `TOTAL_COMPENSATION_SQL` — the shared aggregate expressions, also used by
  `analytics_service._get_contribution_by_year` and
  `comparison_service._query_dc_plan`, so gross cost is spelled once.
- `build_employer_cost_offsets(rows, policy)` — policy and timing.
- `compute_employer_cost(conn, …)` — the full gross/offset/net series for one
  scenario database.

The offset is built from `vesting_service.project_forfeitures_for_connection`,
the same projection the Vesting screens report, so offsets tie to
`VestingService` totals exactly. Gross match and core tie to
`fct_employer_match_events` / `int_employer_core_contributions` to the cent.

## Surfaces

### Studio — Cost Comparison

Additive only. The scenario sidebar, anchor selection, cohort control,
Annual/Cumulative toggle, charts and Multi-Year Cost Matrix all behave exactly
as before, and **with the toggle on Gross the rendered numbers are unchanged**.

Net view adds a vesting schedule selector, a policy selector, a net series on
the cost chart, and *Forfeiture offset* / *Net employer cost* rows in the cost
matrix. All three selections persist in the existing
`planalign_comparison_<workspace>` localStorage entry.

The net view is a **what-if overlay**: it applies one vesting schedule to every
selected scenario rather than reading each scenario's own plan design.

No new endpoint. The page fetches
`GET /workspaces/{id}/analytics/vesting/forfeitures?scenarios=…&schedule_type=…&forfeiture_policy=…`
in parallel with `compareDCPlanAnalytics` and joins on
`(scenario_id, simulation_year)`. Policy and timing semantics stay server-side.

### CLI

```bash
planalign analyze cost --database iso.duckdb
planalign analyze cost --database a.duckdb,b.duckdb --export excel --output cost.xlsx
planalign analyze cost --database iso.duckdb --vesting-schedule cliff_3_year \
    --forfeiture-policy reallocate_to_participants
```

`--database` takes a comma-separated list to compare scenarios in one pass.

### Excel

`--export excel` writes a `Cost_<scenario>` sheet per scenario (per-year gross
match, gross core, gross cost, forfeitures generated, offset applied, net cost,
% of compensation, and the offset-basis reason) plus a `Net_Cost_Comparison`
sheet — the cross-scenario artifact that sells a plan amendment.

## Out of scope

Present-value discounting, admin/recordkeeping fee modeling, and any
restructuring of the Cost Comparison layout or the Vesting screens beyond their
automatic pickup of the corrected basis.
