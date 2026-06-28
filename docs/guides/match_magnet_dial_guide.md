# Match-Magnet Dial — Analyst Guide

**Feature 102** • Audience: analysts configuring voluntary-enrollment behavior

The **match magnet** models the well-documented "defer to the match" behavior: a
fraction of employees who enroll voluntarily choose a deferral rate that exactly
captures the **full employer match** rather than the rate their demographics would
otherwise predict. This guide explains the controls, their defaults, where to set
them, and how they interact with the employer-match ceiling.

> Match magnet affects **voluntary** enrollment only. Auto-enrolled participants
> get their plan-default deferral; the magnet does not change that path.

---

## 1. What the magnet does

For each voluntary enrollee the engine computes:

1. A **demographically-assigned deferral rate** (the rate the enrollment model
   would pick from age/income/job-level segments).
2. A per-employee **match ceiling** — the smallest deferral rate that earns the
   entire employer match for *that* employee under the active match formula.

The magnet then **snaps a deterministic fraction of below-ceiling enrollees up to
the ceiling**. It never lowers a rate: an enrollee already at or above the ceiling
is left unchanged, and so is anyone the magnet does not select. The final rate is
then bounded by the floor (1%) and the configurable cap (`max_deferral_rate`).

The ceiling tracks **whatever match formula is active**, in every match mode
(`deferral_based`, `graded_by_service`, `tenure_based`, `tenure_graded`,
`points_based`). Change the match formula and the ceiling — and therefore where
snapped enrollees land — moves with it.

---

## 2. The three controls

All three live under `enrollment.match_magnet` in the scenario / simulation YAML.

| Control | Meaning | Default | Range |
| :--- | :--- | :--- | :--- |
| `enabled` | Toggle the defer-to-the-match behavior on/off. | `true` | bool |
| `snap_probability` | Fraction of **below-ceiling** voluntary enrollees who snap up to the match ceiling. Higher → more enrollees land exactly at the ceiling and average deferral rises. | `0.45` | `0.0`–`1.0` |
| `max_deferral_rate` | Upper bound on any voluntary deferral rate, including magnet-snapped rates. If the ceiling exceeds this cap, snapped enrollees land at the cap. | `0.10` | `0.01`–`1.0` |

The defaults reproduce prior behavior, so **a scenario that omits the
`match_magnet` block is unchanged**.

---

## 3. Where to set it

### Scenario / simulation YAML

```yaml
enrollment:
  match_magnet:
    enabled: true            # Toggle the defer-to-the-match behavior
    snap_probability: 0.45   # Fraction of below-ceiling enrollees who snap to the ceiling (0.0–1.0)
    max_deferral_rate: 0.10  # Upper bound on voluntary deferral selection (incl. snapped rates)
```

The block is shown commented-out in `config/simulation_config.yaml` (under
`enrollment:`) — uncomment and edit, or add the same block to a scenario file in
`scenarios/`.

### PlanAlign Studio (UI)

The DC-plan editor exposes the same controls; UI values **override** the YAML for
that scenario. The UI fields map to the dbt vars as follows:

| UI / dc_plan field | dbt var | YAML equivalent |
| :--- | :--- | :--- |
| `match_magnet_enabled` | `enrollment_match_magnet_enabled` | `match_magnet.enabled` |
| `match_magnet_probability` | `enrollment_match_magnet_probability` | `match_magnet.snap_probability` |
| `max_voluntary_deferral_percent` | `voluntary_max_deferral_rate` | `match_magnet.max_deferral_rate` |

---

## 4. Interaction with the match ceiling

The ceiling is derived from the **active employer-match formula**, independent of
whether the optional `deferral_match_response` feature is enabled. It is exported
once as the dbt var `employer_match_max_deferral_rate` and resolved per-employee in
SQL by the `resolve_match_magnet_ceiling` macro:

| Match mode | Ceiling source |
| :--- | :--- |
| `deferral_based` | The match-maximizing rate of the active formula (e.g. a 50%-on-first-6% match → 6%; a stretch match to 10% → 10%). |
| `graded_by_service` | Per-employee tier from `employer_match_graded_schedule`, keyed on years of service. |
| `tenure_based` | Per-employee tier from `tenure_match_tiers` (`max_deferral_pct`). |
| `tenure_graded` | Per-employee band from `tenure_graded_bands` (max `employee_max` within the band). |
| `points_based` | Per-employee tier from `points_match_tiers`, keyed on age + tenure points. |
| disabled / unknown | `0` — the magnet is inactive. |

Two consequences worth communicating to stakeholders:

- **Raising the match ceiling raises deferrals.** Stretching a match from
  "first 6%" to "first 10%" raises the ceiling, so snapped enrollees defer 10%
  instead of 6% — average deferral and the 10%+ share both rise.
- **The cap can clip the ceiling.** If the ceiling is above `max_deferral_rate`,
  snapped enrollees land at the cap, not the ceiling. To let enrollees reach a
  10% ceiling, set `max_deferral_rate` to at least `0.10`.

---

## 5. Tuning recipes

- **Counteract declining average deferral in a no-auto-enrollment plan:** raise
  `snap_probability` (e.g. `0.45 → 0.80`). More enrollees defer to the full match.
- **Model a richer match and let participants follow it:** raise the match
  ceiling (formula/tiers) and ensure `max_deferral_rate` ≥ the new ceiling.
- **Turn the behavior off entirely** (e.g. for a sensitivity baseline): set
  `enabled: false`. Voluntary rates then follow demographic assignment only.

---

## 6. Determinism & reproducibility

Snap selection uses a deterministic hash draw, so the same scenario + `random_seed`
produces identical deferral distributions across runs. Changing `snap_probability`
changes *who* snaps in a stable, monotonic way (higher probability ⊇ lower).

---

## 7. Validating a change

Validate match-magnet changes in an **isolated** database (never the shared
`dbt/simulation.duckdb`), over the **full multi-year horizon** — cross-year
deferral drift is invisible in a single-year run. See
`specs/102-match-magnet-dial/quickstart.md` for the full validation playbook.
Quick check, after a batch run writes an isolated `<scenario>.duckdb`:

```sql
SELECT simulation_year,
       ROUND(AVG(employee_deferral_rate), 4)                                  AS avg_deferral,
       ROUND(AVG(CASE WHEN employee_deferral_rate >= 0.10 THEN 1 ELSE 0 END), 4) AS share_10pct_plus
FROM fct_workforce_snapshot
WHERE employment_status = 'active' AND employee_deferral_rate > 0
GROUP BY 1 ORDER BY 1;
```

A higher match ceiling or higher `snap_probability` should produce a strictly
higher `avg_deferral` (and higher `share_10pct_plus` once the ceiling reaches 10%).
