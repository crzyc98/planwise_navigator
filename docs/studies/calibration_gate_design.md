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
| 307 | Development | A, B | yes |
| 311 | Development | A, B | yes |
| 401 | Holdout | A, B, L | yes (S used base 42, see Deviations) |
| 409 | Holdout, seed gap at 25k | L | yes |
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
- **Guardrail with four growth years (2026-11-24).** A 2026–2030 horizon has four growth
  years, so the 80% bar allowed no misses, where it was meant to allow one. Development
  (bases 307 and 311 on A and B, 16 cells) had exactly one year outside 0.5pp in 5 cells,
  by 0.51 to 0.69pp, and passed every other check. The owner approved reading criterion 2
  as at most one year outside 0.5pp, before any holdout ran on A, B or L. The recorded S
  cells have no years outside, so they are unaffected.
- **Sponsor 4.5/3 (2026-11-24).** Reproduction was exact, within 1e-12, in all 16
  development cells. The owner will rerun this cell with the scenario on seed 42.

## Results

Run 2026-11-24 on `main` at `72770b4c`. Each cell used a new workspace and followed
Studio's path through the API: upload the census, run 2026–2030, search, Apply, then a
fresh full run at the base seed and one at base+10. A and L kept the prefilled census
date of 2024-12-31. B was confirmed as 2025-12-31, because its hires run into December
2025.

**All 16 holdout cells on A, B and L pass every check.** The gate stays open for the
sponsor census: the owner still has to rerun S 4.5/3 and run S 5.5/5.5.

- **Target.** The largest horizon miss in a holdout search is 0.08pp, against 0.25pp.
- **Guardrail.** No holdout cell has a year outside 0.5pp.
- **Apply.** The saved levers match the reported best in every cell.
- **Reproduction.** The fresh full run matches the search's base-seed result within
  1e-12 in all 32 cells.
- **Unseen seed.** The largest holdout miss is 0.20pp, against 0.50pp.
- **Order.** A higher target gives a higher result on every census and seed.
- **Seed gap at 25k.** Bases 401 and 409 differ by at most 0.01pp on L.

A horizon cell took about 11 minutes on A and B and 15 minutes on L, of which the search
was 6 to 8 minutes, with three or four cells running side by side.

### Holdout (bases 401 and 409)

| Census | Solver | Targets | Base | Search CAGR | Years outside | Seeds | Base-seed run | Unseen-seed run | Pass |
| ------ | ------ | ------- | ---: | ----------: | ------------- | ----- | ------------: | --------------: | ---- |
| A | Horizon | 3.0/3 | 401 | 2.94% | 0 of 4 (worst 0.19pp) | 2.89 / 2.75 / 3.18 | 2.89% | 3.10% | yes |
| A | Horizon | 4.5/3 | 401 | 4.43% | 0 of 4 (worst 0.21pp) | 4.37 / 4.23 / 4.68 | 4.37% | 4.58% | yes |
| A | Horizon | 5.5/5.5 | 401 | 5.53% | 0 of 4 (worst 0.17pp) | 5.55 / 5.34 / 5.70 | 5.55% | 5.67% | yes |
| B | Horizon | 3.0/3 | 401 | 2.94% | 0 of 4 (worst 0.35pp) | 2.99 / 2.84 / 2.99 | 2.99% | 2.94% | yes |
| B | Horizon | 4.5/3 | 401 | 4.42% | 0 of 4 (worst 0.37pp) | 4.48 / 4.32 / 4.47 | 4.48% | 4.42% | yes |
| B | Horizon | 5.5/5.5 | 401 | 5.47% | 0 of 4 (worst 0.11pp) | 5.48 / 5.46 / 5.47 | 5.48% | 5.46% | yes |
| L | Horizon | 3.0/3 | 401 | 3.03% | 0 of 4 (worst 0.08pp) | 2.97 / 3.03 / 3.09 | 2.97% | 3.05% | yes |
| L | Horizon | 4.5/3 | 401 | 4.52% | 0 of 4 (worst 0.07pp) | 4.46 / 4.52 / 4.58 | 4.46% | 4.55% | yes |
| L | Horizon | 5.5/5.5 | 401 | 5.46% | 0 of 4 (worst 0.15pp) | 5.38 / 5.47 / 5.52 | 5.38% | 5.47% | yes |
| L | Horizon | 3.0/3 | 409 | 3.04% | 0 of 4 (worst 0.08pp) | 3.09 / 2.97 / 3.06 | 3.09% | 3.11% | yes |
| L | Horizon | 4.5/3 | 409 | 4.53% | 0 of 4 (worst 0.06pp) | 4.59 / 4.46 / 4.55 | 4.59% | 4.61% | yes |
| L | Horizon | 5.5/5.5 | 409 | 5.46% | 0 of 4 (worst 0.12pp) | 5.55 / 5.37 / 5.46 | 5.55% | 5.53% | yes |
| A | Pay per head alone | 3.0/3 | 401 | 3.07% | 0 of 4 (worst 0.36pp) | one seed | 3.07% | 3.20% | yes |
| A | Pay per head alone | 4.5/3 | 401 | 4.54% | 0 of 4 (worst 0.26pp) | one seed | 4.54% | 4.65% | yes |
| L | Pay per head alone | 3.0/3 | 401 | 3.00% | 0 of 4 (worst 0.38pp) | one seed | 3.00% | 2.97% | yes |
| L | Pay per head alone | 4.5/3 | 401 | 4.50% | 0 of 4 (worst 0.27pp) | one seed | 4.50% | 4.46% | yes |

"Pay per head alone" searches one seed, so its years are judged on that seed.

### Development (bases 307 and 311)

| Census | Solver | Targets | Base | Search CAGR | Years outside | Seeds | Base-seed run | Unseen-seed run | Pass |
| ------ | ------ | ------- | ---: | ----------: | ------------- | ----- | ------------: | --------------: | ---- |
| A | Horizon | 3.0/3 | 307 | 3.05% | 0 of 4 (worst 0.29pp) | 3.05 / 3.08 / 3.01 | 3.05% | 3.10% | yes |
| A | Horizon | 4.5/3 | 307 | 4.54% | 0 of 4 (worst 0.28pp) | 4.54 / 4.57 / 4.50 | 4.54% | 4.59% | yes |
| A | Horizon | 5.5/5.5 | 307 | 5.58% | 0 of 4 (worst 0.28pp) | 5.55 / 5.62 / 5.57 | 5.55% | 5.59% | yes |
| A | Horizon | 3.0/3 | 311 | 2.97% | 0 of 4 (worst 0.24pp) | 2.89 / 2.92 / 3.09 | 2.89% | 3.03% | yes |
| A | Horizon | 4.5/3 | 311 | 4.45% | 0 of 4 (worst 0.25pp) | 4.38 / 4.41 / 4.57 | 4.38% | 4.52% | yes |
| A | Horizon | 5.5/5.5 | 311 | 5.44% | 0 of 4 (worst 0.26pp) | 5.45 / 5.40 / 5.46 | 5.45% | 5.51% | yes |
| B | Horizon | 3.0/3 | 307 | 3.02% | 0 of 4 (worst 0.10pp) | 3.07 / 2.88 / 3.11 | 3.07% | 3.13% | yes |
| B | Horizon | 4.5/3 | 307 | 4.51% | 0 of 4 (worst 0.10pp) | 4.56 / 4.37 / 4.60 | 4.56% | 4.63% | yes |
| B | Horizon | 5.5/5.5 | 307 | 5.45% | 0 of 4 (worst 0.42pp) | 5.44 / 5.35 / 5.57 | 5.44% | 5.66% | yes |
| B | Horizon | 3.0/3 | 311 | 2.99% | 1 of 4 (worst 0.68pp) | 2.90 / 3.03 / 3.04 | 2.90% | 2.75% | yes |
| B | Horizon | 4.5/3 | 311 | 4.49% | 1 of 4 (worst 0.69pp) | 4.40 / 4.53 / 4.54 | 4.40% | 4.24% | yes |
| B | Horizon | 5.5/5.5 | 311 | 5.52% | 1 of 4 (worst 0.53pp) | 5.40 / 5.53 / 5.61 | 5.40% | 5.43% | yes |
| A | Pay per head alone | 3.0/3 | 307 | 3.00% | 1 of 4 (worst 0.60pp) | one seed | 3.00% | 3.09% | yes |
| A | Pay per head alone | 4.5/3 | 307 | 4.49% | 1 of 4 (worst 0.51pp) | one seed | 4.49% | 4.49% | yes |
| A | Pay per head alone | 3.0/3 | 311 | 3.02% | 0 of 4 (worst 0.46pp) | one seed | 3.02% | 3.18% | yes |
| A | Pay per head alone | 4.5/3 | 311 | 4.42% | 0 of 4 (worst 0.19pp) | one seed | 4.42% | 4.62% | yes |

Pass here uses the guardrail reading under Deviations. Five cells have one year outside
0.5pp. On B at base 311 the search named the hire pay ratio floor, but its control run
with the floor relaxed missed by more (0.54pp), so the floor did not cause the miss.

### Sponsor census (base 42)

| Census | Targets | Search CAGR | Years outside | Seeds | Base-seed run | Unseen-seed run | Pass |
| ------ | ------- | ----------: | ------------: | ----- | ------------: | --------------: | ---- |
| S | 3.0/3 | 3.00% | 0 of 4 (worst 0.13pp) | 3.17 / 2.87 / 2.97 | 3.17% (seed 42) | 3.01% (seed 52) | yes |
| S | 4.5/3 | 4.48% | 0 of 4 (worst 0.17pp) | 4.50 / 4.45 / 4.49 | 4.53% (seed 52, search 4.50%) | 4.69% (seed 42) | no: reproduction off 0.03pp |
