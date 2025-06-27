# Asset-Based Multi-Year Simulation Architecture

**Status**: Idea/Consideration
**Date**: 2025-06-27
**Context**: Current `run_multi_year_simulation` is a single large operation

## Problem Statement

The current multi-year simulation is implemented as one monolithic Dagster operation (`run_multi_year_simulation`) that:

- Runs for potentially hours (2025-2029 = 5 years of simulation)
- Has limited observability into individual year progress
- Can't restart from a specific year if something fails
- Doesn't leverage Dagster's dependency graph visualization
- Makes debugging specific year issues more difficult

## Proposed Solution: Year-Level Assets

### Architecture Overview

Break the monolithic operation into individual year assets:

```
baseline_workforce_validated
    ↓
simulation_year_2025
    ↓
simulation_year_2026
    ↓
simulation_year_2027
    ↓
simulation_year_2028
    ↓
simulation_year_2029
    ↓
multi_year_simulation_summary
```

### Implementation Approach

#### 1. Dynamic Asset Generation
```python
def create_simulation_year_asset(year: int, previous_year: int = None):
    """Factory function to create a simulation asset for a specific year."""

    @asset(name=f"simulation_year_{year}")
    def simulation_year_asset(context: AssetExecutionContext) -> YearResult:
        # Load config from YAML
        config = load_simulation_config()

        # Run existing single-year logic
        year_result = run_year_simulation_for_multi_year(context, year, config)

        # Create snapshot
        run_dbt_snapshot_for_year(context, year, "end_of_year")

        return year_result

    return simulation_year_asset

# Generate assets based on config
def create_simulation_assets():
    config = load_simulation_config()
    start_year = config.get('start_year', 2025)
    end_year = config.get('end_year', 2029)

    assets = []
    for year in range(start_year, end_year + 1):
        previous_year = year - 1 if year > start_year else None
        asset_func = create_simulation_year_asset(year, previous_year)
        assets.append(asset_func)

    return assets
```

#### 2. Summary Asset
```python
@asset(deps=simulation_year_assets)
def multi_year_simulation_summary(context: AssetExecutionContext) -> Dict[str, Any]:
    """Aggregate results from all simulation years."""
    # Query database for all year results
    # Provide same summary logging as current approach
    # Return aggregated metrics
```

#### 3. Job Definitions
```python
@job(resource_defs={"dbt": dbt_resource})
def asset_based_multi_year_simulation():
    """Asset-based multi-year simulation with individual year restart capability."""
    pass  # Dagster handles asset materialization automatically
```

## Benefits

### 1. Restart Capability
- Failed at 2027? Restart from there, not from 2025
- Each year is independently materializable
- No need to re-run successful years

### 2. Better Observability
- Each year appears as separate node in Dagster UI
- Clear visual dependency chain
- Individual year progress tracking
- Easier to identify where failures occur

### 3. Granular Debugging
- Isolate issues to specific years
- Independent logging per year
- Easier to test individual years

### 4. Development Benefits
- Different team members can work on different years
- Parallel development of year-specific logic
- Individual asset checks per year

## Trade-offs

### Pros
- Much better debugging and restart experience
- Leverages Dagster's asset system properly
- Cleaner separation of concerns
- Better for iterative development

### Cons
- More complex asset setup
- Configuration needs to be loaded from YAML instead of op config
- Additional complexity in dependency management
- Need to maintain both approaches during transition

## Implementation Steps

1. **Phase 1**: Add configuration loading from YAML
2. **Phase 2**: Create asset factory functions
3. **Phase 3**: Generate year assets dynamically
4. **Phase 4**: Create summary asset
5. **Phase 5**: Add new job definition
6. **Phase 6**: Test with small year range (2025-2026)
7. **Phase 7**: Full testing and validation
8. **Phase 8**: Documentation and migration guide

## Alternative: Hybrid Approach

Could also implement a middle ground:
- Keep existing monolithic job for production
- Add asset-based approach for development/debugging
- Let users choose which approach to use

## Decision Needed

- Do we want to pursue this refactor?
- Should we implement both approaches side-by-side?
- What's the priority vs. other development work?

## Related Files

- `orchestrator/simulator_pipeline.py` - Current implementation
- `config/simulation_config.yaml` - Configuration file
- Various dbt models that would be called by individual year assets
