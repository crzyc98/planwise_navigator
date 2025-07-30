# Story S025-02: Match Event Generation

**Epic**: E025 - Match Engine with Formula Support
**Story Points**: 6
**Priority**: High
**Sprint**: TBD
**Owner**: Platform Team
**Status**: 📋 **PLANNED**

## Story

**As a** system architect
**I want** match calculations to generate events
**So that** we maintain complete audit trails and event sourcing consistency

## Business Context

This story extends the match calculation engine from S025-01 by generating EMPLOYER_MATCH events that integrate with the existing event sourcing architecture. It ensures that all employer match transactions are properly recorded with full context and payload information for compliance auditing and downstream processing. The event generation must maintain high performance while preserving complete traceability.

## Acceptance Criteria

### Event Generation Requirements
- [ ] **Generate EMPLOYER_MATCH events** from match calculations with full payload
- [ ] **Include formula details** in event payload for audit transparency
- [ ] **Support batch event generation** for efficient processing
- [ ] **Integrate with event sourcing architecture** using existing event model
- [ ] **Performance target**: <5 seconds for 10K employees

### Event Payload Completeness
- [ ] **Formula identification** (formula_id, formula_type) in every event
- [ ] **Calculation context** (deferral_rate, eligible_compensation, match_cap_applied)
- [ ] **Effective match rate** for analysis and reporting
- [ ] **Unique event IDs** for proper event tracking

### Integration Points
- [ ] **Use match calculations** from S025-01 as data source
- [ ] **Generate events** in standardized SimulationEvent format
- [ ] **Store events** in fct_yearly_events table for downstream processing

## Technical Specifications

### Event Generation Model

```sql
-- dbt/models/marts/fct_employer_match_events.sql
{{
  config(
    materialized='incremental',
    unique_key=['event_id'],
    on_schema_change='sync_all_columns'
  )
}}

WITH match_calculations AS (
  SELECT * FROM {{ ref('int_employee_match_calculations') }}
  {% if is_incremental() %}
  WHERE simulation_year > (SELECT MAX(simulation_year) FROM {{ this }})
  {% endif %}
),

match_events AS (
  SELECT
    {{ dbt_utils.generate_surrogate_key(['employee_id', 'simulation_year', 'current_timestamp()']) }} as event_id,
    employee_id,
    'EMPLOYER_MATCH' as event_type,
    simulation_year,
    DATE(simulation_year || '-12-31') as effective_date,
    employer_match_amount as amount,
    -- Event payload with complete context
    {
      'event_type': 'EMPLOYER_MATCH',
      'formula_id': formula_id,
      'formula_type': formula_type,
      'deferral_rate': deferral_rate,
      'eligible_compensation': eligible_compensation,
      'annual_deferrals': annual_deferrals,
      'employer_match_amount': employer_match_amount,
      'match_cap_applied': match_cap_applied,
      'effective_match_rate': effective_match_rate,
      'plan_year': simulation_year,
      'calculation_method': 'annual_aggregate',
      'created_by': 'match_engine_v1'
    }::JSON as event_payload,
    CURRENT_TIMESTAMP as created_at,
    'match_engine' as source_system,
    '{{ var("scenario_id", "default") }}' as scenario_id,
    '{{ var("plan_design_id", "standard") }}' as plan_design_id
  FROM match_calculations
  WHERE employer_match_amount > 0
)

SELECT * FROM match_events
```

### Integration with Existing Event Storage

```sql
-- dbt/models/marts/fct_yearly_events.sql (modification)
-- Add EMPLOYER_MATCH events to the unified event stream

WITH employer_match_events AS (
  SELECT
    event_id,
    employee_id,
    event_type,
    effective_date,
    simulation_year,
    amount,
    event_payload,
    created_at,
    source_system,
    scenario_id,
    plan_design_id
  FROM {{ ref('fct_employer_match_events') }}
),

-- Combine with existing events
all_events AS (
  -- Existing event sources
  SELECT * FROM {{ ref('fct_hire_events') }}
  UNION ALL
  SELECT * FROM {{ ref('fct_promotion_events') }}
  UNION ALL
  SELECT * FROM {{ ref('fct_termination_events') }}
  UNION ALL
  SELECT * FROM {{ ref('fct_contribution_events') }}
  -- Add match events
  UNION ALL
  SELECT * FROM employer_match_events
)

SELECT * FROM all_events
ORDER BY effective_date, created_at
```

### Orchestrator Integration

```python
# Integration with orchestrator_mvp/run_multi_year.py

def run_match_event_generation(year: int, config: SimulationConfig) -> Dict[str, Any]:
    """Generate employer match events for a simulation year"""

    logger.info(f"Starting match event generation for year {year}")

    # Execute match event generation model through dbt
    result = execute_dbt_command_streaming(
        ["run", "--select", "fct_employer_match_events"],
        working_dir="dbt"
    )

    if result.returncode != 0:
        raise RuntimeError(f"Match event generation failed for year {year}")

    # Query generated events for validation
    with DuckDBConnection(config.database_path) as conn:
        events_df = conn.execute("""
            SELECT
                event_id,
                employee_id,
                event_type,
                simulation_year,
                amount,
                event_payload,
                created_at
            FROM fct_employer_match_events
            WHERE simulation_year = ?
        """, [year]).df()

    logger.info(f"Generated {len(events_df)} employer match events for year {year}")
    logger.info(f"Total match amount: ${events_df['amount'].sum():,.2f}")

    # Validation checks
    validation_results = validate_match_events(year, config)

    return {
        "events_generated": len(events_df),
        "total_match_amount": events_df['amount'].sum(),
        "validation_results": validation_results,
        "year": year
    }

def validate_match_events(year: int, config: SimulationConfig) -> Dict[str, Any]:
    """Validate generated match events for completeness and accuracy"""

    with DuckDBConnection(config.database_path) as conn:
        validation_results = {}

        # Check event completeness
        completeness_df = conn.execute("""
            SELECT
                COUNT(*) as total_events,
                COUNT(CASE WHEN amount > 0 THEN 1 END) as positive_amount_events,
                COUNT(CASE WHEN event_payload IS NOT NULL THEN 1 END) as events_with_payload,
                AVG(amount) as avg_match_amount,
                SUM(amount) as total_match_cost
            FROM fct_employer_match_events
            WHERE simulation_year = ?
        """, [year]).df()

        validation_results['completeness'] = completeness_df.to_dict('records')[0]

        # Check formula distribution
        formula_df = conn.execute("""
            SELECT
                JSON_EXTRACT(event_payload, '$.formula_type') as formula_type,
                COUNT(*) as event_count,
                SUM(amount) as total_amount,
                AVG(amount) as avg_amount
            FROM fct_employer_match_events
            WHERE simulation_year = ?
            GROUP BY JSON_EXTRACT(event_payload, '$.formula_type')
        """, [year]).df()

        validation_results['formula_distribution'] = formula_df.to_dict('records')

        logger.info(f"Match event validation complete for year {year}: {validation_results}")
        return validation_results
```

### Event Payload Schema

The event payload follows the established SimulationEvent pattern:

```python
# Example event payload structure
{
    "event_type": "EMPLOYER_MATCH",
    "formula_id": "tiered_match",
    "formula_type": "tiered",
    "deferral_rate": 0.05,
    "eligible_compensation": 75000.00,
    "annual_deferrals": 3750.00,
    "employer_match_amount": 2875.00,
    "match_cap_applied": false,
    "effective_match_rate": 0.767,
    "plan_year": 2024,
    "calculation_method": "annual_aggregate",
    "created_by": "match_engine_v1"
}
```

## Test Scenarios

### dbt Tests for Event Generation
```yaml
# dbt/models/marts/schema.yml
models:
  - name: fct_employer_match_events
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - event_id
    columns:
      - name: event_id
        tests:
          - not_null
          - unique
      - name: amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              inclusive: true
      - name: event_payload
        tests:
          - not_null
```

### Test Cases
1. **Event Generation Volume**:
   - Input: 10K employees with match calculations
   - Expected: 8K-9K events (excluding zero matches)
   - Performance: <5 seconds

2. **Event Payload Completeness**:
   - Verify all required payload fields present
   - Validate JSON structure integrity
   - Check formula_id matches active configuration

3. **Event Uniqueness**:
   - Each employee generates exactly one match event per year
   - Event IDs are unique across all events
   - No duplicate events in incremental loads

4. **Integration with Event Stream**:
   - Match events appear in fct_yearly_events
   - Events maintain proper chronological order
   - Event sourcing reconstruction includes matches

5. **Formula Context Preservation**:
   - Simple match events contain correct formula_type
   - Tiered match events include tier calculation details
   - Match cap application properly recorded

## Implementation Tasks

### Phase 1: Core Event Generation
- [ ] **Create match event model** using incremental materialization
- [ ] **Implement event payload structure** with all required context
- [ ] **Add unique event ID generation** for proper tracking
- [ ] **Integrate with existing event storage** in fct_yearly_events

### Phase 2: Orchestrator Integration
- [ ] **Integrate with orchestrator_mvp** multi-year simulation framework
- [ ] **Add event validation logic** for completeness checking
- [ ] **Implement performance monitoring** for generation speed
- [ ] **Add logging and metrics** for operational monitoring

### Phase 3: Testing & Validation
- [ ] **Create comprehensive dbt tests** for event integrity
- [ ] **Add integration tests** with orchestrator_mvp multi-year simulation framework
- [ ] **Performance testing** with large employee populations
- [ ] **Validate event sourcing** reconstruction includes matches

## Dependencies

### Technical Dependencies
- **S025-01**: Core Match Formula Models (provides match calculations)
- **Existing event model** (SimulationEvent structure)
- **Event storage infrastructure** (fct_yearly_events table)
- **orchestrator_mvp multi-year simulation framework** for pipeline integration

### Story Dependencies
- **S025-01**: Core Match Formula Models (must be completed first)

## Success Metrics

### Functionality
- [ ] **Event generation completeness**: All eligible employees have match events
- [ ] **Payload accuracy**: All context information properly captured
- [ ] **Event uniqueness**: No duplicates or missing events
- [ ] **Integration success**: Events flow through existing pipeline

### Performance
- [ ] **Generation speed**: <5 seconds for 10K employees
- [ ] **Memory efficiency**: Incremental loading for large populations
- [ ] **Storage optimization**: Efficient JSON payload structure

## Definition of Done

- [ ] **Match event generation model** implemented with incremental loading
- [ ] **Event payload structure** complete with all required context fields
- [ ] **Integration with orchestrator_mvp** multi-year simulation framework via orchestrator_mvp/run_multi_year.py
- [ ] **Performance targets met**: <5 seconds for 10K employees
- [ ] **Event validation** confirming completeness and accuracy
- [ ] **Integration with event sourcing** verified through reconstruction tests
- [ ] **All test scenarios passing** with comprehensive coverage
- [ ] **Documentation complete** with event payload schema and examples

## Notes

This story bridges the gap between pure calculation (S025-01) and analytical reporting (S025-03) by ensuring all match transactions are properly recorded as events. The incremental loading strategy supports efficient processing of multi-year simulations while maintaining complete audit trails.
