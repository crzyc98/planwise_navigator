# Pay growth study at 25k: design

Frozen before any run, as an addendum to [the pay growth study](pay_growth_design.md)
for #1112. It checks whether the lever effects found there change with workforce size.

## Setup

- Full simulations, one fresh database per cell, on `main` at `dad56791`. That's after the
  2025 hire pay fix (#1125), so census A is rerun here rather than reused.
- Census A (7,505 employees, 2025 to 2035), and a synthetic 25k census made by
  resampling census A with new IDs and up to ±3% pay jitter. The 25k census has the
  same mix as A, so this tests size, not a different workforce.
- Otherwise as the first study: 5.5% headcount growth, Match Census ranges times the
  scale, raises set with `raise_budget`.

## Cells

- Lever contrasts on both censuses, seeds 42 and 7: base (5.5% raises, 0% hire pay
  growth, 1.0x), then each lever moved alone: 9% raises, 5.5% hire pay growth, 2.0x.
- Swing at 25k: 9% raises, 5% hire pay growth, 1.0x, seeds 42, 7 and 13.

## Reported

Each lever's effect by year on both censuses, horizon CAGR, the seed spread in annual
growth, and the swing measures from the first study.

Size changes the conclusions only if a lever's 2035 effect differs between the
censuses by more than 0.5pp, a threshold set before the runs.
