# Pay growth study design

Frozen before any run, for #1111 and #1112. Metrics follow
[the growth metric contract](../guides/growth_metrics.md). The primary metric is
total pay per head.

## Setup

- Full simulations, one fresh database per cell, on `main` at `8f24d1c1`.
- 5.5% headcount growth, with the repo's default config otherwise.
- New-hire ranges are Studio's Match Census ranges times the scale.
- Raises are set with `raise_budget`.
- Seeds 42, 7 and 13 are development seeds. No holdout seed is used.
- The issues asked for 5k and 25k censuses. The chosen censuses are A (7,505
  employees, 2025 to 2035) and B (5,505 employees, high turnover, 2026 to 2035).
  25k isn't covered here.

## #1111: the year-to-year swing

Fixed inputs: 9% raises, 5% hire pay growth, 1.0x scale, seeds 42, 7 and 13, on
both censuses.

Each year's growth is split into parts that sum exactly, with the residual shown:
raises for employees without a promotion, raises for promoted employees,
employment days, leavers' lost pay, hires who stayed, hires who left, last year's
leavers dropping out, and headcount.

## #1112: what drives sustained growth

Grid: raises 5.5, 7 and 9%; hire pay growth 0, 3 and 5.5%; scale 1.0, 1.5 and
2.0x; seeds 42 and 7; both censuses. That's 108 runs.

Reported: CAGR over the horizon and its last five years, each lever's effect by
year with the others held fixed, interactions, and the hire-to-existing pay ratio.

The long-run rule, that growth settles at hire pay growth, counts as holding in a
cell when last-five-year CAGR is within 0.5pp of hire pay growth. That threshold
was set before the runs.
