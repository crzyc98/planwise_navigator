# Epic E068D: Hazard Caches with Automatic Change Detection

## Goal
Cache slow-changing hazard dimensions and rebuild only when parameters change.

## Rationale
Avoid recomputing small dimension tables every run; eliminate hidden drift from parameter changes.

## Scope
- **In**: `dim_*_hazards` persisted tables; hazard_cache_metadata(cache_name, params_hash, built_at); orchestrator pre-check to refresh on hash change.
- **Out**: Business logic of hazards (rates, probabilities remain unchanged).

## Deliverables
- Cache builders for hazard dimension tables
- Metadata table for tracking parameter changes
- Orchestrator hook to compute params_hash = sha256(json(hazard_params))

## Tasks / Stories

### 1. Implement cache SQL models
- Create `dim_promotion_hazards` with computed promotion probabilities
- Create `dim_termination_hazards` with computed turnover rates
- Create `dim_merit_hazards` with computed merit increase probabilities
- Create `dim_enrollment_hazards` with computed enrollment probabilities

### 2. Create hazard cache metadata table
- Write/Update metadata when hazard caches are rebuilt
- Track parameter fingerprints to detect changes
- Store build timestamps and validation checksums

### 3. Implement orchestrator change detection
- Orchestrator check → rebuild if hash differs from cached version
- Compute parameter hash from simulation config and comp_levers.csv
- Skip hazard rebuild if parameters unchanged

## Acceptance Criteria
- Caches rebuild only on parameter changes; metadata updated.
- Event Gen runs unaffected when no parameter changes.
- Performance improvement: 2-5s saved per simulation run when caches hit.

## Implementation Details

### Hazard Cache Models
```sql
-- models/dimensions/dim_promotion_hazards.sql
{{ config(
  materialized='table',
  tags=['HAZARD_CACHE']
) }}

WITH promotion_parameters AS (
  SELECT
    level,
    tenure_band,
    department,
    performance_tier,
    -- Load promotion rates from comp_levers or config
    base_promotion_rate,
    tenure_multiplier,
    performance_multiplier,
    department_adjustment
  FROM {{ ref('int_effective_parameters') }}
  WHERE parameter_type = 'promotion_rates'
),

hazard_calculations AS (
  SELECT
    level,
    tenure_band,
    department,
    performance_tier,
    -- Compute final promotion probability
    LEAST(1.0,
      base_promotion_rate *
      tenure_multiplier *
      performance_multiplier *
      department_adjustment
    ) AS promotion_probability,
    -- Additional hazard metrics
    expected_months_to_promotion,
    confidence_interval_lower,
    confidence_interval_upper
  FROM promotion_parameters
)

SELECT
  level,
  tenure_band,
  department,
  performance_tier,
  promotion_probability,
  expected_months_to_promotion,
  confidence_interval_lower,
  confidence_interval_upper,
  -- Audit fields
  CURRENT_TIMESTAMP AS cache_built_at,
  '{{ var("hazard_params_hash") }}' AS params_hash
FROM hazard_calculations
ORDER BY level, tenure_band, department, performance_tier
```

```sql
-- models/dimensions/dim_termination_hazards.sql
{{ config(
  materialized='table',
  tags=['HAZARD_CACHE']
) }}

WITH termination_parameters AS (
  SELECT
    level,
    tenure_band,
    performance_tier,
    department,
    -- Load termination rates
    base_termination_rate,
    tenure_adjustment,
    performance_adjustment,
    economic_factor,
    seasonal_adjustment
  FROM {{ ref('int_effective_parameters') }}
  WHERE parameter_type = 'termination_rates'
),

hazard_calculations AS (
  SELECT
    level,
    tenure_band,
    performance_tier,
    department,
    -- Compute monthly termination probability
    LEAST(1.0,
      base_termination_rate *
      tenure_adjustment *
      performance_adjustment *
      economic_factor *
      seasonal_adjustment
    ) AS termination_probability,
    -- Derived metrics
    expected_tenure_months,
    hazard_ratio,
    survival_probability_12mo
  FROM termination_parameters
)

SELECT
  level,
  tenure_band,
  performance_tier,
  department,
  termination_probability,
  expected_tenure_months,
  hazard_ratio,
  survival_probability_12mo,
  CURRENT_TIMESTAMP AS cache_built_at,
  '{{ var("hazard_params_hash") }}' AS params_hash
FROM hazard_calculations
ORDER BY level, tenure_band, performance_tier, department
```

### Cache Metadata Tracking
```sql
-- models/meta/hazard_cache_metadata.sql
{{ config(
  materialized='table',
  tags=['CACHE_METADATA']
) }}

SELECT
  cache_name,
  params_hash,
  built_at,
  row_count,
  checksum,
  is_current
FROM (
  VALUES
    ('dim_promotion_hazards', '{{ var("hazard_params_hash") }}', CURRENT_TIMESTAMP,
     (SELECT COUNT(*) FROM {{ ref('dim_promotion_hazards') }}),
     (SELECT MD5(GROUP_CONCAT(promotion_probability ORDER BY level, tenure_band)) FROM {{ ref('dim_promotion_hazards') }}),
     TRUE),

    ('dim_termination_hazards', '{{ var("hazard_params_hash") }}', CURRENT_TIMESTAMP,
     (SELECT COUNT(*) FROM {{ ref('dim_termination_hazards') }}),
     (SELECT MD5(GROUP_CONCAT(termination_probability ORDER BY level, tenure_band)) FROM {{ ref('dim_termination_hazards') }}),
     TRUE),

    ('dim_merit_hazards', '{{ var("hazard_params_hash") }}', CURRENT_TIMESTAMP,
     (SELECT COUNT(*) FROM {{ ref('dim_merit_hazards') }}),
     (SELECT MD5(GROUP_CONCAT(merit_probability ORDER BY level, department)) FROM {{ ref('dim_merit_hazards') }}),
     TRUE),

    ('dim_enrollment_hazards', '{{ var("hazard_params_hash") }}', CURRENT_TIMESTAMP,
     (SELECT COUNT(*) FROM {{ ref('dim_enrollment_hazards') }}),
     (SELECT MD5(GROUP_CONCAT(enrollment_probability ORDER BY level, tenure_band)) FROM {{ ref('dim_enrollment_hazards') }}),
     TRUE)
) AS cache_status(cache_name, params_hash, built_at, row_count, checksum, is_current)
```

### Orchestrator Integration
```python
# navigator_orchestrator/hazard_cache_manager.py
import hashlib
import json
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

class HazardCacheManager:
    def __init__(self, config: SimulationConfig, dbt_runner: DbtRunner):
        self.config = config
        self.dbt_runner = dbt_runner
        self.logger = logging.getLogger(__name__)

    def compute_hazard_params_hash(self) -> str:
        """Compute SHA256 hash of all parameters affecting hazard calculations."""

        # Collect parameters from multiple sources
        params = {
            'simulation_config': {
                'target_growth_rate': self.config.target_growth_rate,
                'termination_rates': self.config.termination_rates,
                'promotion_rates': getattr(self.config, 'promotion_rates', {}),
                'merit_rates': getattr(self.config, 'merit_rates', {}),
            }
        }

        # Include comp_levers.csv if exists
        comp_levers_path = Path("dbt/seeds/comp_levers.csv")
        if comp_levers_path.exists():
            comp_levers_df = pd.read_csv(comp_levers_path)
            params['comp_levers'] = comp_levers_df.to_dict('records')

        # Include any hazard-specific configuration files
        hazard_config_path = Path("config/hazard_parameters.yaml")
        if hazard_config_path.exists():
            with open(hazard_config_path) as f:
                hazard_config = yaml.safe_load(f)
                params['hazard_config'] = hazard_config

        # Create deterministic hash
        params_json = json.dumps(params, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(params_json.encode()).hexdigest()

    def get_cached_params_hash(self) -> Optional[str]:
        """Get the parameters hash from the most recent cache build."""

        try:
            # Query cache metadata table
            query = """
            SELECT params_hash
            FROM hazard_cache_metadata
            WHERE is_current = TRUE
            LIMIT 1
            """

            result = self.dbt_runner.execute_query(query)
            if result and len(result) > 0:
                return result[0]['params_hash']

        except Exception as e:
            self.logger.warning(f"Could not retrieve cached params hash: {e}")

        return None

    def should_rebuild_caches(self) -> bool:
        """Determine if hazard caches need to be rebuilt."""

        current_hash = self.compute_hazard_params_hash()
        cached_hash = self.get_cached_params_hash()

        needs_rebuild = current_hash != cached_hash

        self.logger.info(f"Hazard cache check: current_hash={current_hash[:8]}..., cached_hash={cached_hash[:8] if cached_hash else 'None'}")
        self.logger.info(f"Hazard caches need rebuild: {needs_rebuild}")

        return needs_rebuild

    def rebuild_hazard_caches(self) -> None:
        """Rebuild all hazard cache tables."""

        self.logger.info("Rebuilding hazard caches...")

        current_hash = self.compute_hazard_params_hash()

        # Set the parameters hash for dbt models
        extra_vars = {"hazard_params_hash": current_hash}

        # Rebuild cache tables
        cache_models = [
            "dim_promotion_hazards",
            "dim_termination_hazards",
            "dim_merit_hazards",
            "dim_enrollment_hazards"
        ]

        for model in cache_models:
            self.logger.info(f"Rebuilding {model}...")
            result = self.dbt_runner.execute_command(
                ["run", "--select", model, "--full-refresh"],
                extra_vars=extra_vars
            )

            if not result.success:
                raise HazardCacheError(f"Failed to rebuild {model}: {result.error}")

        # Update metadata table
        self.logger.info("Updating hazard cache metadata...")
        result = self.dbt_runner.execute_command(
            ["run", "--select", "hazard_cache_metadata", "--full-refresh"],
            extra_vars=extra_vars
        )

        if not result.success:
            raise HazardCacheError(f"Failed to update cache metadata: {result.error}")

        self.logger.info("Hazard cache rebuild completed successfully")

    def ensure_hazard_caches_current(self) -> None:
        """Ensure hazard caches are current, rebuilding if necessary."""

        if self.should_rebuild_caches():
            self.rebuild_hazard_caches()
        else:
            self.logger.info("Hazard caches are current, skipping rebuild")


class HazardCacheError(Exception):
    """Exception raised for hazard cache operations."""
    pass
```

### Pipeline Integration
```python
# navigator_orchestrator/pipeline.py
class PipelineOrchestrator:
    def __init__(self, config: SimulationConfig):
        # ... existing initialization
        self.hazard_cache_manager = HazardCacheManager(config, self.dbt_runner)

    def execute_single_year_simulation(self, simulation_year: int) -> SingleYearExecutionSummary:
        """Execute single year simulation with hazard cache optimization."""

        start_time = time.time()
        stage_results = []

        try:
            # Pre-flight: Ensure hazard caches are current
            self.logger.info("Checking hazard cache currency...")
            self.hazard_cache_manager.ensure_hazard_caches_current()

            # Execute normal workflow stages
            for stage in self.workflow_stages:
                stage_result = self.execute_workflow_stage(stage, simulation_year)
                stage_results.append(stage_result)

                if not stage_result.success:
                    raise PipelineExecutionError(f"Stage {stage.name} failed")

            # ... rest of execution logic

        except Exception as e:
            # ... error handling
```

### Performance Monitoring
```sql
-- models/monitoring/hazard_cache_performance.sql
{{ config(materialized='view') }}

WITH cache_stats AS (
  SELECT
    cache_name,
    built_at,
    row_count,
    LAG(built_at) OVER (PARTITION BY cache_name ORDER BY built_at) AS previous_build,
    LAG(row_count) OVER (PARTITION BY cache_name ORDER BY built_at) AS previous_count
  FROM hazard_cache_metadata
  WHERE is_current = TRUE
),

performance_metrics AS (
  SELECT
    cache_name,
    built_at,
    row_count,
    DATEDIFF('hour', previous_build, built_at) AS hours_since_last_rebuild,
    row_count - previous_count AS row_count_change,
    CASE
      WHEN hours_since_last_rebuild > 24 THEN 'STALE'
      WHEN row_count_change > row_count * 0.1 THEN 'SIGNIFICANT_CHANGE'
      ELSE 'CURRENT'
    END AS cache_status
  FROM cache_stats
)

SELECT
  cache_name,
  built_at,
  row_count,
  hours_since_last_rebuild,
  row_count_change,
  cache_status,
  CASE
    WHEN cache_status = 'STALE' THEN 'Consider rebuilding - cache is over 24 hours old'
    WHEN cache_status = 'SIGNIFICANT_CHANGE' THEN 'Verify parameter changes are intentional'
    ELSE 'Cache is current and stable'
  END AS recommendation
FROM performance_metrics
ORDER BY cache_name
```

## Success Metrics
- Cache hit rate: >90% of simulation runs use existing caches
- Rebuild frequency: Only when parameters actually change
- Performance gain: 2-5s saved per run when caches are current
- Memory usage: Hazard tables remain <10MB total size

## Dependencies
- Parameter management system (comp_levers.csv, simulation config)
- dbt incremental models for metadata tracking
- SHA256 hashing for parameter fingerprinting

## Risk Mitigation
- **Stale cache detection**: Monitor cache age and force refresh after threshold
- **Parameter drift**: Comprehensive hash includes all relevant configuration sources
- **Cache corruption**: Checksum validation and automatic rebuild on validation failure
- **Performance regression**: Fallback to real-time hazard calculation if cache unavailable

---

**Epic**: E068D
**Parent Epic**: E068 - Database Query Optimization
**Status**: 🔴 NOT STARTED
**Priority**: Medium
**Estimated Effort**: 2 story points
**Target Performance**: 2-5s improvement per simulation run through cache optimization
