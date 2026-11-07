# Pay growth study at 25k: results

Results for [the 25k design](pay_growth_25k_design.md). All 19 cells finished without
errors, each in its own fresh database.

## Summary

- **Size doesn't change the lever effects.** Every lever's 2035 effect is within 0.10pp
  between the two censuses, well inside the 0.5pp threshold set before the runs.
- **A larger workforce swings less.** At 25k, annual growth varies about half as much
  between seeds, and the year-to-year swing is about 0.2pp.
- The 25k census is a resample of census A, so this tests size only. A 25k census with a
  different mix of staff could still behave differently.

## Lever effects by year

Percentage points of annual growth against the base (5.5% raises, 0% hire pay growth,
1.0x), mean of seeds 42 and 7.

| Change        | Census | 2026  | 2028 | 2030 | 2032 | 2034 | 2035 | Horizon CAGR |
| ------------- | ------ | ----: | ---: | ---: | ---: | ---: | ---: | -----------: |
| Raises 5.5→9% | A      |  2.65 | 2.02 | 1.55 | 1.14 | 0.97 | 0.85 |         1.57 |
| Raises 5.5→9% | 25k    |  2.64 | 2.00 | 1.53 | 1.16 | 0.83 | 0.77 |         1.53 |
| Hire 0→5.5%   | A      |  0.44 | 1.69 | 2.82 | 3.65 | 4.12 | 4.36 |         2.76 |
| Hire 0→5.5%   | 25k    |  0.45 | 1.78 | 2.82 | 3.63 | 4.31 | 4.46 |         2.80 |
| Scale 1→2x    | A      | 10.99 | 6.92 | 4.72 | 3.49 | 2.20 | 1.96 |         5.10 |
| Scale 1→2x    | 25k    | 11.14 | 7.18 | 4.74 | 3.30 | 2.47 | 2.01 |         5.17 |

These match the first study's pattern: raises fade, hire pay growth builds, and scale
is a one-time step.

## Seed variation

| Measure                                        | Census A | 25k  |
| ---------------------------------------------- | -------: | ---: |
| Mean seed spread in a year at the base, pp     |     0.35 | 0.20 |
| Largest seed spread in a year at the base, pp  |     1.03 | 0.60 |

The swing cell at 25k (9% raises, 5% hire pay growth, 1.0x, seeds 42, 7 and 13):

| Measure                                   | 25k  |
| ----------------------------------------- | ---: |
| Standard deviation around the trend, pp   | 0.19 |
| Seed standard deviation in a year, pp     | 0.14 |
| Largest seed spread in a year, pp         | 0.61 |
| Seed range in horizon CAGR, pp            | 0.03 |

The first study measured 0.47pp and 0.40pp for the first two on census A, on older code,
so they aren't a paired comparison. The fall is about what more people would give:
sampling noise shrinks with the square root of headcount, and 25k is about 3.3 times
larger.

## What this means

- The calibration levers and bounds from the #1114 spec don't need to change with size.
- A 0.5pp annual guardrail is easier to hold on a large workforce. On small ones, the
  three-seed average matters more.
