# Calibration search: objective, levers and pay scale

Decision record for #1114. Evidence is in
[the pay growth results](../../docs/studies/pay_growth_results.md). Metrics follow
[the growth metric contract](../../docs/guides/growth_metrics.md).

Status: direction accepted, details below awaiting review.

## Decisions

### Objective

- The search targets horizon CAGR of the chosen metric, within 0.25pp. Seeds moved
  horizon CAGR by at most 0.22pp.
- Each year has a guardrail of 0.5pp around the target. That's about the size of the
  normal swing, so one run with fixed inputs will still miss it in some years.
- To keep years inside the guardrail, each candidate is scored on the average of three
  seeds. Raises stay one number for the whole horizon. The result also shows each seed,
  because a single full run can still leave the guardrail in some years.
- A guardrail miss is reported, and it only rejects a candidate when another candidate
  meets the target without one.

### Levers

| Lever                      | Role                                   | Default bounds     |
| -------------------------- | -------------------------------------- | ------------------ |
| Hire pay growth            | Sets the sustained rate                | 0–8%               |
| Raise budget               | Handles the early years                | 1–10%              |
| Hire-to-existing pay ratio | Sets the starting level of hire pay    | 90–110%, per #1075 |

Analysts can change all of these bounds. Every run shows which bound stopped the
search. Only a controlled run with that bound relaxed can blame a miss on it (#1115).

New-hire scale leaves the search. It has the largest effect but no stable meaning:
1.0x starts hires at 0.57 of existing pay on one census and 0.27 on another.

### One pay scale

Existing staff and hires use the same scale. This resolves #1126.

Today they don't:
- Staff levels come from `config_job_levels`, which has gaps and a $56k floor. About
  29% of active staff on one census and 60% on the other fit no band. They fall to
  level 1, including staff paid $500k or more. These shares are approximate.
- Hire pay comes from Match Census bands, cut from recent hires only.
- A census level column is read by Match Census and ignored by the simulation.

The scale follows these rules:
- Bands are contiguous. Level 1 has no floor and the top level has no ceiling, so
  everyone gets a level.
- The analyst can enter the scale. Otherwise it's derived from all active employees'
  annualized pay at the 5th, 25th, 50th, 75th, 90th and 97th percentiles.
- A census level column, when present, wins over pay for existing staff.
- Levels are assigned once, at the start. After that only promotions change them.
- The scale must reach the FOUNDATION build. `int_baseline_workforce` is built where
  `job_level_compensation` isn't available today, and the prototype failed on this.

### Hire pay

- Hire pay is set per level, on annualized pay, as a ratio of existing staff at that
  level in the start year. After that it moves only with hire pay growth. It must not
  follow simulated existing pay each year, or hire pay growth would stop being an
  independent lever.
- A level with fewer than 20 active staff uses its band's midpoint.
- The live ratio is reported each year, by level and overall. It's a report, not a
  constraint, because it's expected to drift as staff mix changes.

### Budget and ties

- 12 evaluations by default, up to 25. Each uses the same database, as #1124 allows.
- Three seeds per evaluation makes a search about three times slower.
- Ties are broken in order: smallest CAGR miss, fewest guardrail misses, smallest move
  from the starting inputs, lowest raises, lowest hire pay growth.

### Cost

Cost means total pay summed over the horizon. No trade-off view is included in this
work.

## Prototype evidence

One scale for staff and hires, derived from all active employees, at 1.0x. Figures are
horizon CAGR with the last five years in brackets, averaged over seeds 42 and 7, plus
the hire-to-existing ratio at the start and end. The prototype ran on the study commit,
so census A's first year still has the #1125 underpayment.

| Census | Raises | Hire pay growth | Current                       | One scale                 |
| ------ | -----: | --------------: | ----------------------------- | ------------------------- |
| A      |   5.5% |            5.5% | 2.52 (3.65), 0.57→0.89        | 3.95 (4.63), 0.68→0.95    |
| A      |     9% |              0% | 1.31 (0.84), 0.55→0.55        | 2.52 (1.67), 0.66→0.59    |
| B      |   5.5% |            5.5% | -4.43 (-2.68), 0.27→0.66      | 3.58 (4.30), 0.78→0.94    |
| B      |     9% |              0% | -4.26 (-3.79), 0.26→0.38      | 2.43 (1.79), 0.76→0.60    |

The two censuses now behave alike, and census B's falling pay disappears. Headcount
was unchanged. The prototype didn't measure the shift in promotions or merit by level,
or a census with a level column.

## Rollout

1. One pay scale (#1126), opt-in.
2. Hire-to-existing ratio (#1075).
3. The solver (#1115), with result reports.

Each step is opt-in. Changing Studio's defaults needs separate approval. Results for
existing scenarios will change once a scenario opts in, and calibrations need rerunning.
Validation repeats the prototype on both censuses, then at 25k.

## Open for review

- Whether a census level column should win over pay.
- The 20-employee threshold for sparse levels.
