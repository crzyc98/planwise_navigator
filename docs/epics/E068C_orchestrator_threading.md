# Epic E068C: Orchestrator Threading & Parallelization

## Goal
Stop per-model loops; invoke one dbt run per stage/year with threads so dbt's DAG parallelizes safe nodes. Optional cohort sharding for Event Generation.

## Rationale
Current pipeline enforces single-thread execution; cores idle during most operations.

## Scope
- **In**: Add threads to dbt_runner.execute_command; replace loops with single selectors per stage; optional event_shards fan-out with deterministic union.
- **Out**: SQL content changes (E068A/B).

## Deliverables
- `pipeline.py` diff: per-stage/year single call with --threads 6.
- Optional: shard launcher (hash(employee_id)%N) and final union writer.

## Implementation Notes
- **Determinism** via stable RNG (E068F), one-writer rule, explicit ORDER BY.
- **Tags**: EVENT_GENERATION, STATE_ACCUMULATION, etc.

## Tasks / Stories

### 1. dbt_runner.execute_command threads parameter
- Add threads: int parameter to execute_command method
- Pass-through to dbt command line: --threads {threads}
- Update all call sites to specify thread count

### 2. Replace per-model loops with selector tags
- Replace individual model execution loops with single selector calls
- Use dbt tags: tag:EVENT_GENERATION, tag:STATE_ACCUMULATION
- Maintain deterministic execution order within each stage

### 3. Add config for threading and sharding
- Add dbt_threads: 6 to simulation config
- Add optional event_shards: 4/8 for large-scale processing
- Configure based on target hardware capabilities

### 4. Implement optional event sharding
- Shard writer names: events_y{t}_shard{i}
- Final union model writes canonical table
- Hash-based employee assignment for determinism

## Acceptance Criteria
- CPU utilization during stages ≥ 80% sustained.
- Total wall time drops toward ~150–180s (with E068A/B).
- No DuckDB write-lock warnings in logs.

## Runbook

```bash
# Single call per stage/year with threading
dbt run --select tag:EVENT_GENERATION --vars '{"simulation_year": 2028}' --threads 6
```

## Implementation Details

### Enhanced dbt_runner with Threading
```python
# navigator_orchestrator/dbt_runner.py
class DbtRunner:
    def __init__(self, dbt_project_dir: Path, threads: int = 1):
        self.dbt_project_dir = dbt_project_dir
        self.threads = threads
        self.logger = logging.getLogger(__name__)

    def execute_command(
        self,
        command: List[str],
        simulation_year: Optional[int] = None,
        threads: Optional[int] = None,
        **kwargs
    ) -> DbtCommandResult:
        """Execute dbt command with optional threading and variables."""

        # Use provided threads or instance default
        thread_count = threads or self.threads

        # Build command with threading
        full_command = ["dbt"] + command + ["--threads", str(thread_count)]

        # Add variables if provided
        if simulation_year:
            vars_dict = {"simulation_year": simulation_year}
            vars_dict.update(kwargs.get("extra_vars", {}))
            full_command += ["--vars", json.dumps(vars_dict)]

        self.logger.info(f"Executing: {' '.join(full_command)} (threads={thread_count})")

        # Execute with streaming output
        return self._execute_with_streaming(full_command)

    def run_models_by_tag(
        self,
        tag: str,
        simulation_year: int,
        threads: Optional[int] = None
    ) -> DbtCommandResult:
        """Run all models with specified tag in parallel."""
        return self.execute_command(
            ["run", "--select", f"tag:{tag}"],
            simulation_year=simulation_year,
            threads=threads
        )

    def run_stage_models(
        self,
        stage: WorkflowStage,
        simulation_year: int,
        threads: Optional[int] = None
    ) -> List[DbtCommandResult]:
        """Run all models for a workflow stage with optimal threading."""
        results = []

        if stage == WorkflowStage.EVENT_GENERATION:
            # Single call for all event generation
            result = self.run_models_by_tag("EVENT_GENERATION", simulation_year, threads)
            results.append(result)

        elif stage == WorkflowStage.STATE_ACCUMULATION:
            # Single call for all state accumulation
            result = self.run_models_by_tag("STATE_ACCUMULATION", simulation_year, threads)
            results.append(result)

        elif stage == WorkflowStage.VALIDATION:
            # Validation can run in parallel
            result = self.run_models_by_tag("VALIDATION", simulation_year, threads)
            results.append(result)

        else:
            # Legacy per-model execution for other stages
            for model in stage.models:
                result = self.execute_command(
                    ["run", "--select", model],
                    simulation_year=simulation_year,
                    threads=1  # Single thread for safety
                )
                results.append(result)

        return results
```

### Updated Pipeline Orchestrator
```python
# navigator_orchestrator/pipeline.py
class PipelineOrchestrator:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.dbt_threads = getattr(config, 'dbt_threads', 6)  # Default to 6 threads
        self.event_shards = getattr(config, 'event_shards', 1)  # Default no sharding
        self.dbt_runner = DbtRunner(
            dbt_project_dir=Path("dbt"),
            threads=self.dbt_threads
        )

    def execute_workflow_stage(
        self,
        stage: WorkflowStage,
        simulation_year: int
    ) -> StageExecutionResult:
        """Execute a workflow stage with optimal threading."""
        start_time = time.time()
        stage_logger = self._get_stage_logger(stage, simulation_year)

        try:
            stage_logger.info(f"Starting {stage.name} for year {simulation_year} (threads={self.dbt_threads})")

            # Execute stage with threading
            if stage in [WorkflowStage.EVENT_GENERATION, WorkflowStage.STATE_ACCUMULATION]:
                results = self._execute_parallel_stage(stage, simulation_year)
            else:
                results = self._execute_sequential_stage(stage, simulation_year)

            # Validate results
            failed_commands = [r for r in results if not r.success]
            if failed_commands:
                raise PipelineExecutionError(f"Stage {stage.name} failed", failed_commands)

            execution_time = time.time() - start_time
            stage_logger.info(f"Completed {stage.name} in {execution_time:.1f}s")

            return StageExecutionResult(
                stage=stage,
                simulation_year=simulation_year,
                success=True,
                execution_time=execution_time,
                command_results=results
            )

        except Exception as e:
            execution_time = time.time() - start_time
            stage_logger.error(f"Failed {stage.name} after {execution_time:.1f}s: {e}")

            return StageExecutionResult(
                stage=stage,
                simulation_year=simulation_year,
                success=False,
                execution_time=execution_time,
                error=str(e)
            )

    def _execute_parallel_stage(
        self,
        stage: WorkflowStage,
        simulation_year: int
    ) -> List[DbtCommandResult]:
        """Execute stage with dbt parallelization."""

        if stage == WorkflowStage.EVENT_GENERATION and self.event_shards > 1:
            return self._execute_sharded_event_generation(simulation_year)
        else:
            # Single parallel execution per stage
            return self.dbt_runner.run_stage_models(
                stage,
                simulation_year,
                threads=self.dbt_threads
            )

    def _execute_sharded_event_generation(self, simulation_year: int) -> List[DbtCommandResult]:
        """Execute event generation with optional sharding for large datasets."""
        results = []

        # Execute sharded event generation in parallel
        for shard_id in range(self.event_shards):
            result = self.dbt_runner.execute_command(
                ["run", "--select", f"events_y{simulation_year}_shard{shard_id}"],
                simulation_year=simulation_year,
                threads=1,  # One thread per shard to avoid contention
                extra_vars={"shard_id": shard_id, "total_shards": self.event_shards}
            )
            results.append(result)

        # Execute final union writer
        union_result = self.dbt_runner.execute_command(
            ["run", "--select", "fct_yearly_events"],
            simulation_year=simulation_year,
            threads=1  # Single writer
        )
        results.append(union_result)

        return results

    def execute_multi_year_simulation(
        self,
        start_year: int,
        end_year: int
    ) -> MultiYearExecutionSummary:
        """Execute multi-year simulation with threading optimization."""

        total_start_time = time.time()
        year_results = {}

        try:
            for year in range(start_year, end_year + 1):
                self.logger.info(f"Starting simulation for year {year} with {self.dbt_threads} threads")

                year_start_time = time.time()
                year_summary = self.execute_single_year_simulation(year)
                year_execution_time = time.time() - year_start_time

                year_results[year] = YearExecutionResult(
                    year=year,
                    success=year_summary.success,
                    execution_time=year_execution_time,
                    stage_results=year_summary.stage_results
                )

                if not year_summary.success:
                    raise PipelineExecutionError(f"Year {year} simulation failed")

                self.logger.info(f"Completed year {year} in {year_execution_time:.1f}s")

            total_execution_time = time.time() - total_start_time

            return MultiYearExecutionSummary(
                start_year=start_year,
                end_year=end_year,
                success=True,
                total_execution_time=total_execution_time,
                year_results=year_results,
                threading_config={
                    "dbt_threads": self.dbt_threads,
                    "event_shards": self.event_shards
                }
            )

        except Exception as e:
            total_execution_time = time.time() - total_start_time
            self.logger.error(f"Multi-year simulation failed after {total_execution_time:.1f}s: {e}")

            return MultiYearExecutionSummary(
                start_year=start_year,
                end_year=end_year,
                success=False,
                total_execution_time=total_execution_time,
                year_results=year_results,
                error=str(e)
            )
```

### Configuration Updates
```yaml
# config/simulation_config.yaml - Threading configuration
performance:
  # Threading configuration
  dbt_threads: 6  # Optimize for 16 vCPU box (leave headroom for OS)
  max_parallel_years: 1  # Sequential year processing for determinism

  # Optional event sharding for large datasets
  event_sharding:
    enabled: false
    shard_count: 4  # Hash-based employee sharding

  # Memory management
  memory_limit_gb: 8.0
  enable_query_optimization: true

workflow:
  # Stage-based execution with tags
  stages:
    initialization:
      models: ["stg_*"]
      threading: sequential

    foundation:
      models: ["int_baseline_*", "int_compensation_*"]
      threading: parallel
      tags: ["FOUNDATION"]

    event_generation:
      threading: parallel
      tags: ["EVENT_GENERATION"]

    state_accumulation:
      threading: parallel
      tags: ["STATE_ACCUMULATION"]

    validation:
      threading: parallel
      tags: ["VALIDATION"]
```

### Optional Event Sharding Implementation
```sql
-- models/events/events_y2025_shard0.sql (example shard)
{{ config(
  materialized='table',
  tags=['EVENT_GENERATION_SHARD']
) }}

-- Only process employees where hash(employee_id) % total_shards = shard_id
WITH shard_cohort AS (
  SELECT *
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND {{ hash_shard('employee_id', var('total_shards')) }} = {{ var('shard_id') }}
),

-- ... rest of event generation logic for this shard

-- models/events/fct_yearly_events.sql (union writer)
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  tags=['EVENT_GENERATION']
) }}

{% if var('event_shards', 1) > 1 %}
  -- Union sharded results
  {% for shard_id in range(var('event_shards')) %}
    SELECT * FROM {{ ref('events_y' ~ var('simulation_year') ~ '_shard' ~ shard_id) }}
    {% if not loop.last %}UNION ALL{% endif %}
  {% endfor %}
{% else %}
  -- Single non-sharded event generation
  {{ event_generation_sql() }}
{% endif %}
```

## Success Metrics
- CPU utilization: Target ≥80% during parallel stages
- Wall-clock time reduction: 40-60% improvement in total runtime
- Thread efficiency: Linear scaling up to hardware thread limit
- Deterministic results: Identical outputs regardless of threading level

## Dependencies
- E068A (Fused events) - Provides tags for parallel execution
- E068B (State accumulation) - Provides tags for parallel execution
- DuckDB thread safety - Ensures concurrent reads don't cause corruption
- Hardware specifications - 16 vCPU box provides threading headroom

## Risk Mitigation
- **Resource contention**: Monitor CPU and memory usage, adjust thread counts
- **DuckDB locks**: Use single writer pattern, avoid concurrent writes to same tables
- **Determinism loss**: Maintain explicit ordering and stable RNG across threads
- **Debug complexity**: Provide single-threaded mode for debugging

---

**Epic**: E068C
**Parent Epic**: E068 - Database Query Optimization
**Status**: 🔴 NOT STARTED
**Priority**: High
**Estimated Effort**: 3 story points
**Target Performance**: 40-60% improvement through parallelization
