# Contract: `fit_report.md` sections

**Feature**: 130-promotion-fit-bias | Implements FR-004b, FR-005, FR-006, FR-001d, FR-007, FR-008b, FR-012, FR-017

Rendered by `planalign_fit/report.py`. The report is the artifact an analyst defends a number from, so every routing and verdict decision must be legible in it without reading code.

## 1. Summary table — new row

`_summary` (`report.py:68`) gains a row, always present:

| | |
|---|---|
| Promotion basis | `measured from level_id` / `estimated from raise distribution` / `not fitted — default retained` |

Plus, when either threshold was moved (FR-017):

| | |
|---|---|
| Non-default thresholds | `level-coverage 0.90 (default 0.95)` |

## 2. Promotion hazard section — restructured

`_hazard_section` (`report.py:98`) is shared with termination and stays generic. Promotion gets a preamble whose content depends on the basis.

### `measured`

Today's section, plus one line:

> Job level supplied by the census for **100%** of linked employees; promotions measured directly from level moves.

### `estimated`

Replaces the current upper-bound warning (FR-012). Includes the per-level evidence FR-006 requires at the same detail as the existing cell table:

> No usable `level_id` column (coverage **0%**, threshold 95%), so promotions were separated from ordinary raises by their size. Levels where the two are distinguishable contribute a fitted rate; the rest retain the configured default.
>
> Separating levels cover **91%** of experienced exposure (gate: 50%).

| Level | Exposure | Verdict | Est. rate | Ordinary raise | Promotion raise | Separation | BIC gain |
|---|---:|---|---:|---:|---:|---:|---:|
| 1 | 3,940 | separated | 0.062 | 5.4% | 18.1% | 3.8σ | +412 |
| 2 | 2,380 | separated | 0.058 | 5.6% | 17.9% | 3.1σ | +233 |
| 5 | 310 | **not separated** | — | — | — | 1.2σ | +8 |

A `not separated` row states its reason in the following prose (FR-004b): thin exposure, distance below the floor, BIC did not prefer two components, or EM did not converge.

Expected-event counts render to **one decimal place** on this path — `total_events` is a sum of fractional weights, and `report.py:117`'s `{:,.0f}` would misrepresent 412.7 as an exact tally.

### `not_fitted`

The section is omitted entirely; promotion appears in "Not fitted — defaults retained" instead (FR-007), with a reason naming the exposure gate and the observed share.

## 3. Merit section — revised description

`_merit_section` (`report.py:174`) currently says merit is fitted over employees "who stayed and were not promoted." That is no longer true on any path (FR-008).

> Fitted as the promotion-weighted median year-over-year compensation growth of employees who stayed, net of the configured COLA. Each employee is weighted by how likely their raise was an ordinary one, so a probable promotion contributes little and a certain promotion contributes nothing.

On the `not_fitted` path, one added sentence (FR-008b):

> Promotions could not be distinguished from ordinary raises in this census, so the weighting could not be sharpened. Some promotion raises may remain in the merit pool, biasing it upward.

## 4. Data warnings — replaced

The warning at `runner.py:334-341` ("the fitted promotion hazard is an upper bound") is **deleted**, not reworded (FR-012). It describes behavior that will no longer exist.

Replacements, emitted only when applicable:

| Condition | Warning |
|---|---|
| Coverage in `(0, threshold)` | `level_id` is present but populated for only **N%** of linked employees, below the 95% threshold. It was ignored and promotions were estimated instead — a partially populated column would otherwise mix two different definitions of promotion in one fit. |
| Basis `not_fitted` | Promotions could not be distinguished from ordinary raises in enough of this population to publish a rate. The configured promotion hazard is retained unchanged. |
| Some levels not separated, basis `estimated` | Levels **N, M** retain their default promotion rate; the raise distribution there did not resolve into two components. |
| Threshold moved (FR-017) | The **<name>** threshold was set to **X** rather than its default **Y**. |

## 5. Method section — new paragraph

`_method_section` (`report.py:246`) gains a paragraph after "Hazard fitting", present on every run so the method is documented whether or not it was used:

> **Promotion classification.** Where the census carries job levels for at least 95% of linked employees, a promotion is a move to a higher level. Otherwise level is derived from compensation banding, which makes any band-crossing raise look like a promotion — so instead the year-over-year raise distribution is fitted per level as two components: ordinary raises near COLA plus merit, and promotion raises near the configured promotion increase. Each employee's probability of belonging to the promotion component becomes their weight in the promotion hazard, and its complement their weight in the merit fit, so the two estimates are identified together rather than off each other. A level contributes a fitted rate only where the two components are genuinely distinguishable — at least two pooled standard deviations apart, with a two-component model preferred on BIC.

## Test surface

`fit_report.md` is asserted against in `tests/test_parameter_fitting.py`. Contract tests:

1. Every path renders a "Promotion basis" row with the matching value.
2. The string `upper bound` appears nowhere in a report produced on any path.
3. `not_fitted` puts promotion in the unfittable table and omits the hazard section.
4. `estimated` renders one per-level verdict row per job level.
5. A moved threshold appears in both the summary and the warnings.
6. The merit section never claims promotions were excluded.
