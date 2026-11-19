# Calibration default gate (#1093): design

Frozen before any run. The thresholds, seeds and cells below stay fixed. A change after
the first run needs a new design and an unused seed.

## Why

Studio already uses these defaults: total pay per head as the growth metric, and, for
new workspaces, the horizon search with one pay scale (#1141). Until now they were checked
on 5k–7.5k censuses and one seed each at 25k. This gate checks the whole path
(search, Apply, then a fresh full simulation) on every census we hold, plus one
sponsor census. If a cell fails, the defaults are revisited. They are not changed
without the owner's approval.

## Setup

- `main` at the commit recorded in the results. One fresh database per cell, under
  `DATABASE_PATH`, and never the shared `dbt/simulation.duckdb`.
- Horizon 2026–2030, 3% headcount growth unless a cell says otherwise. Everything else
  stays at Studio's defaults for a new workspace: 12 evaluations, 3 seeds per
  evaluation, a 0.5pp guardrail and the bounds in `specs/1114-calibration-search`.

| Census | Rows | Note |
| ------ | ---: | ---- |
| A | 7,505 | `data/census_preprocessed.parquet` |
| B | 5,505 | `data/parquet/census_preprocessed_2025.parquet`, high turnover |
| L | 25,000 | `data/census_synthetic_25k.parquet`, resampled from A |
| S | ~45,000 | A real sponsor census, run by the owner. Only aggregates are reported |

## Cells

Targets are total pay per head CAGR / headcount growth.

| Solver | Targets | Censuses |
| ------ | ------- | -------- |
| Horizon (default) | 3.0/3, 4.5/3, 5.5/5.5 | A, B, L, S |
| Total pay per head alone (`new_hire_scale`) | 3.0/3, 4.5/3 | A, L |

The 5.5/5.5 cell repeats the sponsor case that #1107 started from.

## Seed ledger

The horizon search uses seeds base, base+1 and base+2. The unseen-seed check uses
base+10. Each holdout base is used once. Seeds already spent: 7, 13, 29, 42–44, 101, 103,
123, 211, 223, 227, 229, 233, 239, 241, 269, 271, 999.

| Base | Role | Cells | Used |
| ---: | ---- | ----- | ---- |
| 307 | Development | A, B | no |
| 311 | Development | A, B | no |
| 401 | Holdout | A, B, L, S | no |
| 409 | Holdout, seed gap at 25k | L | no |
| 419 | Reserved: one retest after a fix | Any cell that failed | no |

Development runs may lead to fixes. Holdout runs happen only after development has
finished, and on the code that will ship.

## Pass criteria (each cell)

1. **Target.** The mean across seeds of horizon CAGR lands within 0.25pp of the target.
   A miss passes only if the search names the bound that stopped it, and a control
   run with that bound relaxed then reaches the target (#1115).
2. **Guardrail.** At least 80% of years land within 0.5pp on the mean across seeds,
   and the result reports every miss.
3. **Apply.** The levers saved to the scenario match the reported best exactly.
   Match Census is not re-run, so it can't replace the calibrated ranges.
4. **Reproduction.** A fresh full simulation at the base seed matches the search's
   result for that seed: horizon CAGR within 1e-6, with timestamps excluded (main is
   not bit-deterministic).
5. **Unseen seed.** A fresh full simulation at base+10 lands within 0.50pp of the
   target in horizon CAGR. That is the 0.25pp band plus the 0.22pp largest seed swing
   measured so far, rounded up.
6. **Order.** On the same census and seed, a higher target never produces lower
   achieved CAGR.
7. **Seed gap at 25k.** Horizon CAGR for bases 401 and 409 on L differs by at most 0.25pp.

Timing is reported but not gated, at the owner's direction.

## Outcome

- **All holdout cells pass:** the defaults stay, #1093 closes, and #1107 can close.
- **Any holdout fails:** file an issue with the cell and its numbers, fix it, then rerun
  only the failed cells at base 419. A second failure goes to the owner.

## Deviations

- **Census S seeds (2026-11-13).** The first S run used base 42 (seeds 42-44), the
  scenario's old default, instead of 401. S had never been calibrated, so the run is kept:
  every S cell uses base 42, with 52 as its unseen seed. The 4.5/3 search ran at base 52
  (seeds 52-54) because the scenario was left on seed 52, so its unseen seed is 42. Studio's default run budget is
  20 evaluations, not 12.

## Results

| Census | Targets | Search CAGR | Years outside | Seeds | Base-seed run | Unseen-seed run | Pass |
| ------ | ------- | ----------: | ------------: | ----- | ------------: | --------------: | ---- |
| S | 3.0/3 | 3.00% | 0 of 4 (worst 0.13pp) | 3.17 / 2.87 / 2.97 | 3.17% (seed 42) | 3.01% (seed 52) | yes |
| S | 4.5/3 | 4.48% | 0 of 4 (worst 0.17pp) | 4.50 / 4.45 / 4.49 | 4.53% (seed 52, search 4.50%) | 4.69% (seed 42) | no: reproduction off 0.03pp |
