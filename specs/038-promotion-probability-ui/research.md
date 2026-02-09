# Research: Promotion Hazard Configuration UI

## Research Question 1: What persistence pattern should be used for promotion hazard parameters?

**Decision**: Use the **band configuration CSV-direct pattern** — read/write seed CSV files directly via a dedicated API service, not the workspace YAML pattern.

**Rationale**: The promotion hazard seeds (`config_promotion_hazard_base.csv`, `config_promotion_hazard_age_multipliers.csv`, `config_promotion_hazard_tenure_multipliers.csv`) are consumed directly by `dim_promotion_hazards.sql` via `{{ ref('stg_config_promotion_hazard_base') }}`. Writing to the CSV seeds ensures the simulation uses the saved values without any additional export/sync step. This is the same pattern used for age/tenure band configuration.

**Alternatives considered**:
- Workspace YAML pattern (used for job level compensation): Rejected because the YAML values require an `export.py` step to become dbt variables, and the hazard model reads from seeds directly — the YAML path would require modifying `dim_promotion_hazards.sql` to accept dbt variable overrides.
- Hybrid (YAML + CSV sync): Rejected as unnecessary complexity for 3 small config files.

## Research Question 2: What is the existing band config pattern to replicate?

**Decision**: Replicate the 4-layer band configuration pattern:

1. **Pydantic models** (`planalign_api/models/promotion_hazard.py`): Data classes with Field validators
2. **Service layer** (`planalign_api/services/promotion_hazard_service.py`): CSV read/write via `csv.DictReader`/`DictWriter`, validation logic
3. **Router** (`planalign_api/routers/promotion_hazard.py`): GET/PUT endpoints at `/{workspace_id}/config/promotion-hazards`
4. **Frontend** (`ConfigStudio.tsx` + `api.ts`): State management, load/save handlers, editable tables

**Rationale**: The band config pattern is production-tested and follows all constitution principles (modular, type-safe, single-responsibility). Replicating it ensures consistency and reduces code review risk.

## Research Question 3: Where to insert the UI section?

**Decision**: Insert a new "Promotion Hazard" section **after line 2395** in `ConfigStudio.tsx` (after Market Positioning closes, before the Compensation section wrapper closes). This places it at the bottom of the Compensation tab.

**Rationale**: The Compensation tab already contains Job Level Compensation and Market Positioning. Promotion hazard parameters relate to compensation/career progression and fit logically here. Placing it after Market Positioning (the last current subsection) avoids disrupting existing UI flow.

## Research Question 4: What validation rules apply?

**Decision**:
- **base_rate**: 0.00–1.00 (displayed as 0–100%). Must be non-negative.
- **level_dampener_factor**: 0.00–1.00 (displayed as 0–100%). Must be non-negative.
- **age_multipliers**: Non-negative decimals. 6 rows expected (matching age bands). Band labels are read-only.
- **tenure_multipliers**: Non-negative decimals. 5 rows expected (matching tenure bands). Band labels are read-only.
- No cross-field validation needed (the formula `base_rate * tenure * age * max(0, 1 - dampener*(level-1))` handles edge cases gracefully).

**Rationale**: Simple per-field constraints match the band config validation approach. The promotion formula naturally handles zero values (produces zero probability).
