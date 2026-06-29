# Contract: Configuration → dbt vars

The orchestrator config surface (Pydantic) and the dbt var surface it exports. This is the interface between analyst-facing configuration and the SQL pipeline.

## YAML (`config/simulation_config.yaml`)

```yaml
eligibility:
  waiting_period_days: 30            # existing
  new_hire_ineligible_pct: 0.0       # NEW — float 0.0–1.0, default 0.0
  new_hire_eligibility_match_census: false  # NEW — bool, default false
```

## Pydantic (`EligibilitySettings`)

| Field | Type | Default | Constraint |
|-------|------|---------|-----------|
| `new_hire_ineligible_pct` | `float` | `0.0` | `Field(default=0.0, ge=0.0, le=1.0)` |
| `new_hire_eligibility_match_census` | `bool` | `False` | — |

**Contract guarantees**:
- A value outside `[0.0, 1.0]` raises `ValidationError` at load (FR-011) — never silently clamped.
- Omitting either field yields the no-op default (FR-013).

## dbt vars (via `to_dbt_vars` in `planalign_orchestrator/config/export.py`)

| dbt var | Source | Default in SQL |
|---------|--------|----------------|
| `new_hire_ineligible_pct` | `cfg.eligibility.new_hire_ineligible_pct` | `var('new_hire_ineligible_pct', 0.0)` |
| `new_hire_eligibility_match_census` | `cfg.eligibility.new_hire_eligibility_match_census` | `var('new_hire_eligibility_match_census', false)` |

**Contract guarantees**:
- Vars are exported only when set, but every SQL consumer supplies the no-op default in `var(...)`, so an un-exported var behaves identically to the default.
- Both vars pass through the pipeline like other enrollment vars (no special casing in the orchestrator beyond the export map).
