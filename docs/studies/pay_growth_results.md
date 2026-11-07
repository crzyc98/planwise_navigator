# Pay growth study results

Results for #1111 and #1112, run to [the frozen design](pay_growth_design.md). All
114 cells finished without errors. Each ran in its own fresh database, so the
stale rows fixed in #1124 can't affect them.

## Summary

- **Raises buy growth that fades.** Moving raises from 5.5% to 9% adds 2.6pp in the
  first year and 0.7pp by 2035.
- **Hire pay growth builds.** Moving it from 0% to 5.5% adds 0.6pp in the first year
  and 4.2pp by 2035, and that effect is still rising.
- **Scale is a one-time step.** Doubling it adds 10.9pp in the first year and 2.0pp
  by 2035. The same scale means different things on each census: at 1.0x, hires
  start at 0.57 of existing pay on census A and 0.27 on census B.
- **The long-run rule isn't reached by 2035.** It held in 5 of 27 cells on census A
  and 1 of 27 on census B. The direction is right, but ten years isn't long enough.
- **The annual swing is mostly turnover, and about as large as seed variation.**
  Raises barely contribute. No defect explains it.
- **Two defects turned up**, filed as #1125 and #1126. Neither was fixed or
  corrected for here.

## Limits

- 25k isn't covered, so #1112 stays open for that.
- The grid uses two seeds per cell and #1111 uses three, so seed figures are rough.
- Census A starts in 2025, so its first-year figures include #1125.
- Census B results mostly reflect #1126. Its hires are paid so far below existing
  staff that its negative growth says little about a typical plan. Its lever
  effects are still useful.

## #1111: the year-to-year swing

Inputs: 9% raises, 5% hire pay growth, 1.0x scale. Figures are percentage points of
total pay per head growth, averaged over seeds 42, 7 and 13. Every part sums to
growth, with a largest residual of about 1e-12.

Census A:

| Year | Growth | Raises | Promoted raises | Days | Leavers | Hires stayed | Hires left | Last year's leavers | Headcount | Seed spread |
| ---- | -----: | -----: | --------------: | ---: | ------: | -----------: | ---------: | ------------------: | --------: | ----------: |
| 2026 |   2.18 |   7.15 |            0.93 | 3.64 |   -4.62 |         7.01 |       1.43 |               -8.15 |     -5.21 |        0.26 |
| 2027 |   3.55 |   7.18 |            0.97 | 4.73 |   -4.77 |         7.30 |       1.47 |               -8.13 |     -5.21 |        1.56 |
| 2028 |   2.87 |   7.16 |            0.99 | 4.71 |   -4.72 |         7.07 |       1.41 |               -8.53 |     -5.22 |        1.01 |
| 2029 |   3.49 |   7.21 |            0.90 | 4.86 |   -4.69 |         7.21 |       1.56 |               -8.34 |     -5.21 |        0.81 |
| 2030 |   3.63 |   7.17 |            0.96 | 4.92 |   -4.72 |         7.47 |       1.59 |               -8.55 |     -5.21 |        0.73 |
| 2031 |   3.68 |   7.19 |            0.89 | 5.01 |   -4.80 |         7.55 |       1.59 |               -8.53 |     -5.21 |        1.05 |
| 2032 |   4.07 |   7.23 |            0.83 | 5.05 |   -4.57 |         7.75 |       1.57 |               -8.58 |     -5.21 |        0.14 |
| 2033 |   4.44 |   7.23 |            0.88 | 5.05 |   -4.48 |         7.80 |       1.70 |               -8.52 |     -5.21 |        0.81 |
| 2034 |   4.16 |   7.20 |            0.89 | 5.02 |   -4.65 |         7.79 |       1.65 |               -8.54 |     -5.21 |        0.63 |
| 2035 |   4.16 |   7.22 |            0.90 | 5.23 |   -4.59 |         7.63 |       1.56 |               -8.58 |     -5.21 |        0.72 |

"Days" is existing staff moving from part of a year to a full year, mostly last
year's hires.

The swing, after removing each seed's trend:

| Measure                                   | Census A | Census B |
| ----------------------------------------- | -------: | -------: |
| Standard deviation around the trend, pp   |     0.47 |     0.36 |
| Mean change from one year to the next, pp | 0.49–0.85 | 0.60–0.74 |
| Seed standard deviation in a year, pp     |     0.40 |     0.35 |
| Seed range in horizon CAGR, pp            |     0.17 |     0.13 |

Share of the swing by part:

| Part                | Census A | Census B |
| ------------------- | -------: | -------: |
| Days                |      32% |       6% |
| Last year's leavers |      28% |      44% |
| Hires who stayed    |      20% |       1% |
| Leavers             |       9% |      44% |
| Raises, both kinds  |       9% |       8% |
| Hires who left      |       3% |      -4% |

**Cause:** who joins and leaves, at what pay and on what date. Raises and headcount
are nearly flat every year. The swing is about the size of the seed variation, so
much of it is sampling of those cohorts. Horizon CAGR varies far less between seeds.

The study doesn't split level mix out of hire pay, so that part of the #1111
outcome is only covered in total. The low 2026 figure on census A is likely #1125:
that year's "days" part is the smallest, because the 2025 cohort was underpaid.

## #1112: what drives sustained growth

### Lever effects by year

Percentage points of annual growth, averaged over the other two levers.

Census A:

| Change        | 2026 | 2027 | 2028 | 2029 | 2030 | 2031 | 2032 | 2033 | 2034 | 2035 |
| ------------- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Raises 5.5→9% | 2.58 | 2.11 | 1.81 | 1.57 | 1.31 | 1.10 | 0.94 | 0.86 | 0.78 | 0.69 |
| Hire 0→5.5%   | 0.64 | 1.51 | 2.05 | 2.59 | 3.07 | 3.41 | 3.72 | 3.91 | 4.06 | 4.24 |
| Scale 1→2x    | 10.89 | 9.43 | 7.40 | 5.94 | 5.06 | 4.25 | 3.69 | 2.98 | 2.31 | 2.03 |

Census B:

| Change        | 2027 | 2028 | 2029 | 2030 | 2031 | 2032 | 2033 | 2034 | 2035 |
| ------------- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Raises 5.5→9% | 2.70 | 2.47 | 2.24 | 1.93 | 1.72 | 1.43 | 1.24 | 1.03 | 0.84 |
| Hire 0→5.5%   | 0.27 | 0.73 | 1.18 | 1.67 | 2.05 | 2.60 | 2.94 | 3.32 | 3.67 |
| Scale 1→2x    | 5.43 | 5.03 | 4.81 | 4.74 | 4.38 | 4.36 | 3.98 | 3.70 | 3.43 |

### Interactions

Each figure is the extra effect of moving two levers together, from low to high.
All are small next to the main effects, so the levers are close to additive.

| Pair           | A, CAGR | A, last five | B, CAGR | B, last five |
| -------------- | ------: | -----------: | ------: | -----------: |
| Raises × hire  |   -0.19 |        -0.28 |   -0.19 |        -0.31 |
| Raises × scale |   -0.15 |        -0.03 |   -0.27 |        -0.30 |
| Hire × scale   |    0.48 |         0.27 |    0.59 |         0.68 |

### Grid

CAGR over the horizon, with the last five years in brackets. Mean of seeds 42 and 7,
which differ by at most 0.22pp.

Census A:

| Raises | Hire pay growth |        1.0x |       1.5x |       2.0x |
| -----: | --------------: | ----------: | ---------: | ---------: |
|   5.5% |              0% | -0.25 (-0.22) | 2.73 (1.60) | 4.95 (2.72) |
|   5.5% |              3% | 1.22 (1.83) | 4.36 (3.75) | 6.68 (4.91) |
|   5.5% |            5.5% | 2.52 (3.65) | 5.78 (5.64) | 8.18 (6.82) |
|     7% |              0% | 0.40 (0.21) | 3.33 (2.01) | 5.53 (3.13) |
|     7% |              3% | 1.83 (2.19) | 4.92 (4.09) | 7.22 (5.26) |
|     7% |            5.5% | 3.08 (3.95) | 6.31 (5.93) | 8.69 (7.13) |
|     9% |              0% | 1.31 (0.84) | 4.18 (2.61) | 6.34 (3.72) |
|     9% |              3% | 2.67 (2.72) | 5.71 (4.60) | 7.98 (5.77) |
|     9% |            5.5% | 3.87 (4.39) | 7.04 (6.37) | 9.40 (7.57) |

Census B:

| Raises | Hire pay growth |        1.0x |       1.5x |       2.0x |
| -----: | --------------: | ----------: | ---------: | ---------: |
|   5.5% |              0% | -6.24 (-5.38) | -3.89 (-3.20) | -1.98 (-1.61) |
|   5.5% |              3% | -5.29 (-3.97) | -2.74 (-1.56) | -0.71 (0.17) |
|   5.5% |            5.5% | -4.43 (-2.68) | -1.73 (-0.08) | 0.42 (1.76) |
|     7% |              0% | -5.41 (-4.72) | -3.12 (-2.63) | -1.26 (-1.09) |
|     7% |              3% | -4.50 (-3.39) | -2.02 (-1.06) | -0.03 (0.62) |
|     7% |            5.5% | -3.68 (-2.17) | -1.04 (0.35) | 1.06 (2.15) |
|     9% |              0% | -4.26 (-3.79) | -2.07 (-1.81) | -0.27 (-0.33) |
|     9% |              3% | -3.41 (-2.56) | -1.03 (-0.34) | 0.90 (1.28) |
|     9% |            5.5% | -2.64 (-1.42) | -0.10 (0.99) | 1.94 (2.73) |

Active average CAGR stayed within about 0.06pp of total pay per head in every cell.

On census A, 5.5% raises, 5.5% hire pay growth and 1.5x comes closest to a sustained
5.5%: 5.78% over the horizon and 5.64% in the last five years. Its hire-to-existing
ratio moves from 0.85 to 0.96. No cell on census B reaches 5.5%.

### When the long-run rule holds

The frozen test is last-five-year CAGR within 0.5pp of hire pay growth.

- **Census A:** held in 5 of 27 cells. They are 5.5% and 7% raises at 5.5% hire
  growth and 1.5x, 5.5% and 7% raises at 0% hire growth and 1.0x, and 9% raises at
  3% hire growth and 1.0x.
- **Census B:** held in 1 of 27, 9% raises at 0% hire growth and 2.0x.

A pass doesn't show a cell has settled. The passing cells have last-year
hire-to-existing ratios from about 0.62 to 0.96, and the ratio is still moving, so
some may only be passing through the threshold. The gap
between annual growth and hire pay growth is shrinking: on average it fell from
2.17pp in the three years to 2032 to 1.20pp in the three years to 2035 on census A,
and from 4.89pp to 3.70pp on census B.

Within this horizon the rule mostly fails because the starting hire-to-existing
ratio is still working through the workforce. Higher scale gives growth above hire
pay growth on census A, in 20 of 27 cells. Census B, with the lowest ratios, stays
below it in every cell. The study doesn't show where growth would settle after 2035.

## What this means for #1114

These are recommendations for that review, not decisions.

- **Objective:** horizon CAGR with annual guardrails. Horizon CAGR varied by at most
  0.22pp across seeds, while single years moved by up to 1.6pp. Guardrails need to
  allow for that swing.
- **Levers:** search hire pay growth for the sustained rate and raises for the early
  years. A raises-only search can't hold a target late in a horizon.
- **Scale:** replace it with a hire-to-existing pay ratio, as #1075 proposes. Scale
  has the largest effect but no stable meaning between censuses. #1126 should be
  settled in the same decision.
- **Before relying on first-year results:** decide #1125.
