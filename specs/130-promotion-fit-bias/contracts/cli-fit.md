# Contract: `planalign fit` CLI surface

**Feature**: 130-promotion-fit-bias | Implements FR-015, FR-016, FR-017, FR-005

## New options

Added to `planalign_cli/commands/fit.py::run_fit`, alongside the existing `--credibility-k` and `--min-exposure`.

| Flag | Type | Default | Help text |
|---|---|---|---|
| `--level-coverage-threshold` | `float` | `0.95` | Share of linked employees that must carry a job level for the census column to be treated as authoritative. Below this, promotions are estimated from the raise distribution instead. |
| `--separation-exposure-gate` | `float` | `0.50` | Share of exposure that must sit in job levels where promotions are distinguishable from ordinary raises before a promotion hazard is published at all. |

**No flag exposes the separation test itself** (FR-016). `SEPARATION_MIN_DISTANCE` and the BIC criterion are module constants in `planalign_fit/promotion.py` with no CLI, config, or environment path to them.

## Validation

Extends the existing check at `fit.py:98`:

```python
if credibility_k < 0 or min_exposure < 0:
    ...exit(EXIT_BAD_INPUT)
```

Both new thresholds must satisfy `0 < value <= 1`. A violation prints a specific message naming the offending flag and exits `EXIT_BAD_INPUT` (2). Values are **never silently clamped** — a clamped threshold produces a fit that looks legitimate but answers a different question (spec edge case).

| Input | Behavior |
|---|---|
| `--level-coverage-threshold 0.9` | Accepted; recorded as non-default |
| `--level-coverage-threshold 0` | Rejected, exit 2 |
| `--level-coverage-threshold 1.5` | Rejected, exit 2 |
| `--separation-exposure-gate -0.1` | Rejected, exit 2 |
| Omitted | Default applied; **not** recorded as non-default |

Exit codes are unchanged: `2` bad input, `3` unreadable snapshots, `4` output refused.

## Summary output

`_render_summary` (`fit.py:~125`) gains one row, always present:

```
Promotion basis      measured from level_id (coverage 100%)
Promotion basis      estimated from raise distribution (4 of 5 levels, 91% of exposure)
Promotion basis      not fitted — default retained
```

The third form renders in yellow, matching how the existing "Thin / prior-backed" and "Could not be fitted" rows signal a caveat. An analyst must not have to open `fit_report.md` to learn that their promotion hazard is a default (FR-005, SC-004).

When a threshold was moved off its default, a second row appears:

```
Thresholds moved     level-coverage 0.90 (default 0.95)
```

## Backward compatibility

Every existing invocation keeps working with identical output on a fully-populated census: `--level-coverage-threshold` defaults to 0.95, a complete `level_id` column scores 1.0 coverage, and the run takes the `measured` path — which is bit-for-bit today's behavior (see data-model.md, "Clean-path parity").

The one intentional behavior change for an existing invocation: a census with a **partially** populated `level_id` below 95% coverage now routes to the estimated path where it previously silently mixed measured and band-derived promotions. That is the FR-001c bug fix, and it is loud — the report states the coverage and the route taken (FR-001d).
