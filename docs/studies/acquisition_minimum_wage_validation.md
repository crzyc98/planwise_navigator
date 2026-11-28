# Acquisition and minimum wage validation (#1232)

Before either change is used for a client answer, this checks that each one does what it
says: a baseline, the acquisition alone, the minimum wage alone and both together, each as
a full multi-year simulation in its own database, compared with the baseline that shares
its config and seed.

**Status: passes on both test censuses. The sponsor census has not been run.** It is
not on the development machine, so the owner runs the command below at work. This issue
stays open until those numbers are added here.

## How to run it

```bash
python3 scripts/dev.py -- python scripts/validate_acquisition_minimum_wage.py \
  --census path/to/census.parquet --config path/to/scenario/config.yaml \
  --minimum-wage 21 --headcount 100 --out var/validate-1232/sponsor
```

- The census needs `hourly_rate`, `hours_worked` or `scheduled_hours_per_week`.
- It runs 31 simulations, three side by side (`--jobs`). A 7,505-row census takes about
  eight minutes for all of them. Finished runs are reused if the command is restarted.
- `report.md` and `results.json` land in `--out`. They hold counts, sums and differences
  only, so they are safe to paste into this page.
- The exit code is 1 when any check fails.

## Design

Fixed before any run.

- **Seeds:** 521, 523 and 541. None is in the #1093 seed ledger.
- **Years:** four, from the config's start year (Y).
- **Minimum wage:** one step on 1 July of Y+1.
- **Acquisition:** three groups of 100, so the minimum wage meets a group that joined
  before it (1 October of Y), on its date (1 July of Y+1) and after it (1 April of Y+2).
  The last group is paid 10% below the staff it is sampled from. Those staff are already
  at the minimum, so this is what puts some of its members below it on joining.
- **Edge configs,** each on seed 521 with all four runs: auto-enrollment for all eligible
  employees with no hire date cutoff, a points-based core with two years of minimum
  service, a tenure-graded match, and a 4% raise budget.
- **Tolerances:** events must match exactly, with pay within a cent. Two checks are not
  exact, for the reasons under Findings: census staff after the first join year (within
  1%), and pay under a raise budget (within 0.01%).

## What is checked

| Area | Check |
| ---- | ----- |
| Off | No acquired member, floor event or step summary in the baseline. The baseline is unchanged when the census loses its rate columns |
| Acquisition | Each group joins whole, on its date. No raise, promotion or exit in the join year, and never new-hire turnover |
| Acquisition | Everyone else's events match the baseline through the first join year |
| Acquisition | Year-end headcount is the baseline plus each group, grown at the target rate since it joined |
| Acquisition | Census staff headcount, pay and employer cost stay within 1% of the baseline in later years |
| Minimum wage | Every raise is on the step date, lifts pay to the minimum at unchanged hours, and happens once |
| Minimum wage | Nobody with a rate ends a year below the minimum. The step summary matches the events |
| Minimum wage | Everyone not raised has the same events, pay and employer cost as the baseline, in every year |
| Minimum wage | Raises and promotions in the step year, and hires in every year, match the baseline |
| Both | Members below the minimum are raised on the step date, or on joining if that is later. No member without a rate is raised |
| Both | Headcount is the minimum wage run plus the groups |

"Off means off" is tested against the same code, not against `main` from before the
features. Fourteen other engine changes merged in between, so that comparison would not
isolate these two.

## Results on the test censuses

Run 2026-11-26 on `main` at `cf9e52dd`. Neither census has hours, so each was given a
synthetic `hourly_rate` of pay / 2,080 for people paid under $75,000. The numbers show
that the mechanics hold. They say nothing about a real sponsor's cost.

| Census | Rows | Years | Minimum | Checks passing | Failing |
| ------ | ---: | ----- | ------: | -------------: | ------: |
| A, `data/census_preprocessed.parquet` | 7,505 | 2025–2028 | $22.00 | 198 of 198 | 0 |
| B, `data/parquet/census_preprocessed_2025.parquet` | 5,505 | 2026–2029 | $19.00 | 198 of 198 | 0 |

Each census also has one number that is reported and not judged: the events that differ
under a raise budget.

Default config, range across the three seeds:

| Measure | A | B |
| ------- | - | - |
| People raised by the step, minimum wage alone | 747 to 754 | 513 to 523 |
| Annual pay the step adds on its date | $3.21M to $3.26M | $6.35M to $6.64M |
| Events that differ for anyone not raised | 0 | 0 |
| Members raised on the step date (two groups) | 22 to 28 | 26 to 37 |
| Members raised on joining (third group) | 7 to 13 | 9 to 12 |
| Members raised on the wrong date | 0 | 0 |
| Largest headcount gap from baseline plus groups | 0.4 | 1.6 |
| Largest census staff drift after the first join year | 0.45% | 0.91% |

Final-year effect against the baseline, seed 521:

| Run | A: headcount | A: pay | A: employer cost | B: headcount | B: pay | B: employer cost |
| --- | -----------: | -----: | ---------------: | -----------: | -----: | ---------------: |
| Acquisition | +318 | +4.29% | +4.06% | +320 | +6.67% | +6.79% |
| Minimum wage | 0 | +0.27% | +0.30% | 0 | +1.53% | +1.57% |
| Both | +318 | +4.58% | +4.38% | +320 | +8.38% | +8.54% |

The edge configs pass every check on both censuses.

## Findings

- **Existing staff are exact only through the first join year.** From the next year,
  members sit in the same pool that experienced leavers are drawn from, so a few census
  staff leave in one run and not the other. Census staff headcount, pay and employer cost
  stayed within 0.91% of the baseline. This follows from #1226 ("from the year after they
  join they follow experienced turnover") and is not a defect.
- **Headcount grows from the larger workforce.** Each group grows at the target rate from
  its join date, as organic hires replace members who leave. #1226's acceptance line
  ("the no-acquisition run plus surviving members") describes the join year only.
- **A raise budget spreads a trace of the floor to everyone.** The budget is a share of
  all eligible pay, so lifting some people rescales later raises by about 0.001
  percentage points. Pay of people the floor did not raise moved by 0.0005% (A) and
  0.0018% (B). In the step year itself, raises match the baseline exactly.
- **Simulated hires are not covered,** as designed in #1229. They have no hourly rate, so
  a hire below the minimum is not raised. The step summary counts them as not covered
  (1,821 to 1,839 on A).
- **A group joining late in the year gets no match or core that year** when the plan
  requires 1,000 hours, because only hours after the join date count. On A the group
  joining on 1 October deferred $190k and received nothing. Filed as #1329, which added
  the acquisition setting `join_year_hours_credit: full_year` ("Credit a full year of
  hours" in Studio) to count members as meeting the hours rule in the join year. This
  runner leaves it unset, so its checks still describe the default.

## Still to do

- The owner runs the command on the sponsor census with the sponsor's scenario config and
  adds the report here.
- The owner runs the sponsor's scenario in Studio from start to finish.
