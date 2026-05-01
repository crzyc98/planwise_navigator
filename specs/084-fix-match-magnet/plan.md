# Implementation Plan: Match Formula as Enrollment Deferral Rate Magnet

**Branch**: `084-fix-match-magnet` | **Date**: 2026-04-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/084-fix-match-magnet/spec.md`

## Summary

At enrollment time, employees in plans with a match formula should be drawn toward the match-maximizing deferral rate ("free money" threshold) rather than defaulting purely to a demographic matrix. The fix replaces a hardcoded match clustering CTE in `int_voluntary_enrollment_decision.sql` (which only knew about formula *names*, not actual tier boundaries) and adds the same dynamic match-threshold attractor to `int_proactive_voluntary_enrollment.sql` (which had zero match awareness). Both models will read the actual configured match tiers at dbt compile time via a Jinja namespace pattern already established in `int_deferral_match_response_events.sql`.

## Technical Context

**Language/Version**: SQL (dbt-core 1.8.8 / dbt-duckdb 1.8.1), Jinja2 templating
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, DuckDB 1.0.0
**Storage**: DuckDB (`dbt/simulation.duckdb`) — no schema changes; new audit column only
**Testing**: dbt schema tests + custom SQL tests; pytest fast suite for orchestrator config
**Target Platform**: Linux / macOS work laptop (on-premises)
**Project Type**: Data pipeline — dbt SQL simulation engine
**Performance Goals**: No regression; both models are already `materialized='table'`; Jinja computation is compile-time (zero runtime overhead)
**Constraints**: `--threads 1` for stability; 100K+ employee records; deterministic results required
**Scale/Scope**: Multi-year workforce simulations; enrollment events for entire active workforce per year

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ PASS | Match-adjusted enrollment rates flow into `fct_yearly_events` as immutable enrollment events. Pre-magnet rate preserved as audit column (FR-010). |
| II. Modular Architecture | ✅ PASS | Changes isolated to 2 dbt intermediate models + 1 config file. No new models created. Each CTE has single responsibility. |
| III. Test-First Development | ⚠️ ACTION REQUIRED | Need dbt custom tests validating clustering behavior. Tests must be written before implementation edits (see Phase 1). |
| IV. Enterprise Transparency | ✅ PASS | `raw_deferral_rate` (pre-magnet) and `match_optimized_rate` (post-magnet) both preserved in model output for audit. |
| V. Type-Safe Configuration | ✅ PASS | New vars declared with explicit typed defaults in `dbt_project.yml`. Jinja `var()` calls include fallback defaults. |
| VI. Performance & Scalability | ✅ PASS | Jinja computes `match_max_rate` at compile time — single constant baked into SQL. No runtime per-row computation overhead. |

## Project Structure

### Documentation (this feature)

```text
specs/084-fix-match-magnet/
├── plan.md              ← This file
├── research.md          ← Phase 0 output (below)
├── data-model.md        ← Phase 1 output (below)
├── contracts/           ← Phase 1 output (dbt variable contract)
├── checklists/
│   └── requirements.md
└── tasks.md             ← Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
dbt/
├── dbt_project.yml                                          # +2 new vars
└── models/
    └── intermediate/
        ├── int_voluntary_enrollment_decision.sql            # Replace match_optimization CTE
        └── int_proactive_voluntary_enrollment.sql           # Add match_optimization CTE
```

**Structure Decision**: Pure dbt SQL changes. No new Python modules, no new dbt models, no schema migrations. The orchestrator already exports all required variables (`match_tiers`, `deferral_match_response_match_max_rate`).

---

## Phase 0: Research

*All unknowns resolved. No NEEDS CLARIFICATION items remain.*

---

## research.md

### Decision 1: How to compute match-maximizing deferral rate in Jinja

**Decision**: Use the pre-computed `deferral_match_response_match_max_rate` dbt variable (exported by the Python orchestrator) as the primary source, with a Jinja namespace fallback that iterates `match_tiers` to find the highest `employee_max`.

**Rationale**: The orchestrator already computes and exports this value in `planalign_orchestrator/config/export.py` (line 931). Using it avoids duplicating the computation. The namespace fallback (identical to the pattern in `int_deferral_match_response_events.sql` lines 58–65) handles cases where the DMR feature is not configured and the pre-computed var is absent.

**Alternatives considered**:
- Compute purely in Jinja every time: Works, but the namespace pattern is verbose. Reusing the pre-computed var is simpler and more consistent.
- Add a new Python export function: Unnecessary; the value already exists in `deferral_match_response_match_max_rate`.

---

### Decision 2: Separate hash salt for proactive model's magnet random

**Decision**: The proactive model will use a new hash expression with salt `-match-magnet-` for the magnet probability draw:
```sql
(ABS(HASH(employee_id || '-match-magnet-' || CAST(simulation_year AS VARCHAR))) % 1000) / 1000.0
```

**Rationale**: The proactive model has no `deferral_random` column (unlike the voluntary model). Using a distinct salt ensures the magnet draw is statistically independent from the enrollment probability draw (`-proactive-voluntary-`) and the timing draw (`-proactive-timing-`). Reusing an existing hash column would create correlation between "who enrolls" and "who snaps to match threshold," which is not behaviorally accurate.

**Alternatives considered**:
- Reuse `enrollment_random` as magnet draw: Creates unwanted correlation (employees who barely cross the enrollment threshold would be more/less likely to snap to match rate).
- Add `deferral_random` column to proactive model: Adds complexity; a new hash expression is simpler and self-documenting.

---

### Decision 3: Default magnet probability (0.45)

**Decision**: Default `enrollment_match_magnet_probability` to 0.45 (45%).

**Rationale**: Financial literacy research indicates approximately 40–50% of employees who are aware of a match formula optimize their contribution at enrollment. The post-enrollment `deferral_match_response` upward participation rate defaults to 0.40; enrollment is a more deliberate moment with slightly higher awareness, so 0.45 is appropriate. This is configurable so plan modelers can tune it per scenario.

**Alternatives considered**:
- 0.40 (same as post-enrollment response): Slightly underestimates enrollment-time awareness.
- 0.60: Too high; overstates financial literacy for a general workforce.

---

### Decision 4: Scope limited to deferral-based match formulas

**Decision**: Apply the magnet only when `employer_match_status == 'deferral_based'`. For `graded_by_service`, `tenure_based`, and `points_based` formulas, `match_max_rate` resolves to `0.0` and the magnet is skipped.

**Rationale**: Tenure/points-based formulas have per-employee match thresholds that require employee-level data unavailable at Jinja compile time. Computing them per-row at enrollment time is out of scope for this fix; the existing `int_deferral_match_response_events.sql` handles these post-enrollment. The `WHEN match_max_rate > 0` guard in the CASE expression naturally disables the magnet when `match_max_rate` is 0.0.

**Alternatives considered**:
- Add per-row SQL lookup for tenure-based thresholds: Significantly more complex; deferred to future enhancement.

---

### Decision 5: No changes to int_enrollment_events.sql

**Decision**: `int_enrollment_events.sql` requires no changes.

**Rationale**: Both `int_proactive_voluntary_enrollment` and `int_voluntary_enrollment_decision` are consumed via explicit column selects (not `SELECT *`) in `int_enrollment_events.sql`. Adding `match_optimized_rate` as an audit column to the proactive model output does not break the downstream consumer. The voluntary enrollment model's `enrollment_decisions` CTE already uses `optimized_deferral_rate` as `selected_deferral_rate` — no column name changes in the downstream-visible output.

---

## Phase 1: Design & Contracts

---

## data-model.md

### Modified Model 1: `int_voluntary_enrollment_decision`

**Change type**: CTE replacement (no table schema change — model is `materialized='table'`)

**Before** (`match_optimization` CTE, lines 199–226):
- Branched on `employer_match_active_formula` string value ('tiered_match' vs 'simple_match')
- Applied hardcoded thresholds: 3%, 5%, or 6%
- Probability thresholds hardcoded: 0.3, 0.6, 0.4

**After** (`match_optimization` CTE):

| Field | Source | Notes |
|-------|--------|-------|
| `optimized_deferral_rate` | `selected_deferral_rate` (pass-through) OR `match_max_rate` | Snaps to match max when: magnet enabled AND match_max_rate > 0 AND selected < match_max_rate AND deferral_random < magnet_probability |

**Jinja compile-time variables resolved**:

| Variable | Source | Default |
|----------|--------|---------|
| `enrollment_match_magnet_enabled` | `dbt_project.yml` | `true` |
| `enrollment_match_magnet_probability` | `dbt_project.yml` | `0.45` |
| `employer_match_status` | Orchestrator export | `'deferral_based'` |
| `deferral_match_response_match_max_rate` | Orchestrator export | `none` |
| `match_tiers` | Orchestrator export (UI config) | `[{employee_min:0.00, employee_max:0.03, match_rate:1.00}, {employee_min:0.03, employee_max:0.05, match_rate:0.50}]` |

**Downstream impact**: None. `enrollment_decisions` CTE already reads `optimized_deferral_rate` and outputs it as `selected_deferral_rate`.

---

### Modified Model 2: `int_proactive_voluntary_enrollment`

**Change type**: New CTE inserted between `deferral_rate_selection` and `proactive_enrollment_decisions`

**New CTE `match_optimization`**:

| Field | Source | Notes |
|-------|--------|-------|
| `*` | `deferral_rate_selection` | All existing columns passed through |
| `optimized_deferral_rate` | `selected_deferral_rate` OR `match_max_rate` | Snaps to match max when: magnet enabled AND match_max_rate > 0 AND selected < match_max_rate AND hash draw < magnet_probability |

**Updated `proactive_enrollment_decisions` CTE**:

| Field | Before | After |
|-------|--------|-------|
| Source CTE | `deferral_rate_selection` | `match_optimization` |
| `proactive_deferral_rate` | `GREATEST(0.01, LEAST(0.10, selected_deferral_rate))` | `GREATEST(0.01, LEAST(0.10, optimized_deferral_rate))` |
| `raw_deferral_rate` (audit) | `selected_deferral_rate` | `selected_deferral_rate` (unchanged — pre-magnet) |
| `match_optimized_rate` (new audit) | n/a | `optimized_deferral_rate` |

**Downstream impact**: `int_enrollment_events.sql` uses explicit column select from this model — new `match_optimized_rate` column is safely ignored by the downstream consumer.

---

### Config Change: `dbt/dbt_project.yml`

Two new vars added after line 310 (end of performance optimization settings), in a new named block:

```yaml
  # Match magnet: attract enrollees toward match-maximizing deferral threshold
  enrollment_match_magnet_enabled: true         # Toggle match-threshold attraction at enrollment
  enrollment_match_magnet_probability: 0.45     # Fraction of sub-threshold enrollees who snap to match max
```

---

## contracts/

### dbt Variable Contract: Enrollment Match Magnet

**File**: `specs/084-fix-match-magnet/contracts/dbt-vars.md`

This feature adds two new dbt variables. These are the externally configurable interface for plan modelers.

| Variable | Type | Default | Valid Range | Description |
|----------|------|---------|-------------|-------------|
| `enrollment_match_magnet_enabled` | boolean | `true` | `true` / `false` | Enables or disables the match-threshold attraction effect at enrollment. When `false`, enrollment deferral rates are determined purely by the demographic matrix (pre-fix baseline behavior). |
| `enrollment_match_magnet_probability` | decimal | `0.45` | `0.0` – `1.0` | Fraction of enrollees whose demographic-based rate falls below the match-maximizing rate who will elect exactly the match-maximizing rate instead. Set to `0.0` to disable without touching the enabled flag. Set to `1.0` for a fully match-aware workforce. |

**Consumed by**: `int_voluntary_enrollment_decision.sql`, `int_proactive_voluntary_enrollment.sql`

**Depends on** (read-only, exported by orchestrator):

| Variable | Type | Notes |
|----------|------|-------|
| `employer_match_status` | string | Must be `'deferral_based'` for magnet to activate |
| `deferral_match_response_match_max_rate` | decimal or none | Pre-computed match-maximizing rate; falls back to Jinja tier iteration if absent |
| `match_tiers` | list of `{employee_min, employee_max, match_rate}` | Used in Jinja fallback to compute `match_max_rate` |

**Override example** (scenario-specific):

```yaml
# In scenario config or dbt --vars flag:
enrollment_match_magnet_enabled: true
enrollment_match_magnet_probability: 0.70   # High-literacy workforce scenario
```

---

## Implementation Steps

### Step 0: Write tests first (Constitution III)

Before touching SQL, write a dbt custom test that validates the magnet behavior:

**File**: `dbt/tests/test_enrollment_match_magnet.sql`

Purpose: After running `int_voluntary_enrollment_decision`, assert that when `employer_match_status = 'deferral_based'` and `match_max_rate > 0`, the fraction of enrollees at `selected_deferral_rate = match_max_rate` is within the expected range (approximately `magnet_probability ± 0.10` for populations > 100 employees).

### Step 1: Update `dbt/dbt_project.yml`

Add after line 310 (performance optimization settings block):

```yaml
  # Match magnet: attract enrollees toward match-maximizing deferral threshold
  enrollment_match_magnet_enabled: true         # Toggle match-threshold attraction at enrollment
  enrollment_match_magnet_probability: 0.45     # Fraction of sub-threshold enrollees who snap to match max
```

### Step 2: Update `int_voluntary_enrollment_decision.sql`

**2a.** Add Jinja block after `{{ config(...) }}`, before `WITH`:

```jinja
{# Match magnet: compute match-maximizing deferral rate from configured tiers #}
{% set employer_match_status = var('employer_match_status', 'deferral_based') %}
{% set precomputed_match_max = var('deferral_match_response_match_max_rate', none) %}
{% set match_tiers = var('match_tiers', [
    {'employee_min': 0.00, 'employee_max': 0.03, 'match_rate': 1.00},
    {'employee_min': 0.03, 'employee_max': 0.05, 'match_rate': 0.50}
]) %}
{% set enrollment_match_magnet_enabled = var('enrollment_match_magnet_enabled', true) %}
{% set enrollment_match_magnet_probability = var('enrollment_match_magnet_probability', 0.45) %}

{% if employer_match_status == 'deferral_based' %}
  {% if precomputed_match_max is not none %}
    {% set match_max_rate = precomputed_match_max %}
  {% else %}
    {% set ns = namespace(match_max_rate=0.0) %}
    {% for tier in match_tiers %}
      {% if tier.employee_max is not none and tier.employee_max > ns.match_max_rate %}
        {% set ns.match_max_rate = tier.employee_max %}
      {% endif %}
    {% endfor %}
    {% set match_max_rate = ns.match_max_rate %}
  {% endif %}
{% else %}
  {% set match_max_rate = 0.0 %}
{% endif %}
```

**2b.** Replace `match_optimization` CTE (lines 199–226) with:

```sql
match_optimization AS (
  SELECT
    *,
    CASE
      WHEN {{ enrollment_match_magnet_enabled }}
        AND {{ match_max_rate }} > 0
        AND selected_deferral_rate < {{ match_max_rate }}
        AND deferral_random < {{ enrollment_match_magnet_probability }}
      THEN {{ match_max_rate }}::DECIMAL(5,4)
      ELSE selected_deferral_rate
    END AS optimized_deferral_rate
  FROM deferral_rate_selection
),
```

No changes to `enrollment_decisions` or `summary_metrics` CTEs — they already use `optimized_deferral_rate`.

### Step 3: Update `int_proactive_voluntary_enrollment.sql`

**3a.** Add the same Jinja block (identical to Step 2a) after `{{ config(...) }}`, before `WITH`.

**3b.** Add new `match_optimization` CTE after `deferral_rate_selection` (after line 255):

```sql
match_optimization AS (
  SELECT
    *,
    CASE
      WHEN {{ enrollment_match_magnet_enabled }}
        AND {{ match_max_rate }} > 0
        AND selected_deferral_rate < {{ match_max_rate }}
        AND (ABS(HASH(employee_id || '-match-magnet-' || CAST(simulation_year AS VARCHAR))) % 1000) / 1000.0
            < {{ enrollment_match_magnet_probability }}
      THEN {{ match_max_rate }}::DECIMAL(5,4)
      ELSE selected_deferral_rate
    END AS optimized_deferral_rate
  FROM deferral_rate_selection
),
```

**3c.** Update `proactive_enrollment_decisions` CTE:
- Change `FROM deferral_rate_selection` → `FROM match_optimization`
- Change `GREATEST(0.01, LEAST(0.10, selected_deferral_rate)) as proactive_deferral_rate` → `GREATEST(0.01, LEAST(0.10, optimized_deferral_rate)) as proactive_deferral_rate`
- Change `selected_deferral_rate as raw_deferral_rate` → `selected_deferral_rate as raw_deferral_rate, optimized_deferral_rate as match_optimized_rate`

### Step 4: Verify

```bash
# Rebuild both enrollment models
cd dbt
dbt run --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment \
    --threads 1 --vars "simulation_year: 2025"

# Verify clustering at match threshold
duckdb simulation.duckdb "
SELECT
  ROUND(selected_deferral_rate * 100, 1) AS deferral_pct,
  COUNT(*) AS n,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM int_voluntary_enrollment_decision
WHERE will_enroll = true
GROUP BY 1 ORDER BY 1
"

# Run enrollment pipeline
dbt run --select int_enrollment_events --threads 1 --vars "simulation_year: 2025"

# Confirm no regression downstream
dbt build --threads 1 --vars "simulation_year: 2025" --fail-fast
```

### Step 5: Write commit

```
fix(084): Add match formula magnet to enrollment deferral rate selection

Enrollment deferral rates now reflect the configured match formula threshold.
Previously int_voluntary_enrollment_decision used hardcoded 3%/5%/6% cluster
points based on formula name; int_proactive_voluntary_enrollment had zero match
awareness. Both models now compute match_max_rate dynamically from match_tiers
at dbt compile time (same Jinja namespace pattern as int_deferral_match_response_events).

~45% of enrollees below the match threshold snap to the match-maximizing rate
by default (configurable via enrollment_match_magnet_probability).
```
