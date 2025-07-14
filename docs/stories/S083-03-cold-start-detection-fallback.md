# Story S083-03: Cold Start Detection & Fallback

## Story Overview

**Epic**: E027 - Multi-Year Simulation Reliability & Performance
**Points**: 3
**Priority**: Medium

### Key Improvements (Based on Gemini Analysis)
1. **Fixed table existence checking**: Use dbt macros to safely check table existence before querying
2. **Robust fallback strategies**: Define clear policies for INTERRUPTED state and use custom exceptions
3. **Performance optimization**: Use dedicated metadata table and LIMIT 1 for existence checks
4. **Additional edge cases**: Handle partial failures, concurrent operations, and schema evolution
5. **Better dbt-Dagster integration**: Use dagster-dbt assets and centralize classification logic
6. **Enhanced monitoring**: Use Dagster asset metadata and integrate with real-time alerting

### User Story
**As a** system administrator
**I want** intelligent detection of simulation state
**So that** the system handles fresh vs continuing simulations appropriately

### Problem Statement
The system lacks intelligent detection of simulation state, leading to failures when models expect data that doesn't exist in fresh environments. There are no fallback mechanisms for missing dependencies, causing cascading failures throughout the simulation pipeline.

### Root Cause
Models are designed with implicit assumptions about data availability without proper validation or fallback logic. This creates brittle dependencies that fail catastrophically when prerequisites are missing.

---

## Acceptance Criteria

### Primary Acceptance Criteria
1. **State Detection**: Automatically detect fresh vs continuing simulations
2. **Fallback Mechanisms**: Implement fallback logic for missing dependencies
3. **Initialization Validation**: Validate proper initialization sequence
4. **Graceful Degradation**: Handle missing prior year data without errors
5. **Clear Error Messages**: Provide actionable error messages for unrecoverable failures

### Secondary Acceptance Criteria
1. **Performance**: Detection logic completes in <5 seconds
2. **Reliability**: 99.9% accuracy in state detection
3. **Monitoring**: Log all detection decisions and fallback actions
4. **Documentation**: Clear troubleshooting guide for state detection issues

---

## Technical Specifications

### System State Detection Framework

#### 1. Safe Table Existence Checking Macro
```sql
-- macros/safe_table_query.sql
{% macro safe_table_query(table_name, default_columns, fallback_query) %}
    {% set relation = adapter.get_relation(
        database=target.database,
        schema=target.schema,
        identifier=table_name
    ) %}

    {% if relation is not none %}
        {{ fallback_query }}
    {% else %}
        SELECT
            {% for column in default_columns %}
                {{ column.default_value }} as {{ column.name }}
                {%- if not loop.last -%},{%- endif -%}
            {% endfor %}
        WHERE 1=0  -- Return empty result set with correct schema
    {% endif %}
{% endmacro %}
```

#### 2. Simulation Metadata Table
```sql
-- models/intermediate/int_simulation_metadata.sql
{{ config(
    materialized='incremental',
    unique_key='simulation_year',
    on_schema_change='append_new_columns'
) }}

-- Track simulation completion status and metadata
WITH simulation_status AS (
    SELECT
        {{ var('current_year') }} as simulation_year,
        CURRENT_TIMESTAMP as last_updated,
        'RUNNING' as status,
        0 as workforce_snapshot_count,
        0 as event_count,
        0 as active_employees

    {% if is_incremental() %}
        WHERE {{ var('current_year') }} NOT IN (
            SELECT simulation_year FROM {{ this }}
        )
    {% endif %}
)
SELECT * FROM simulation_status

-- Post-hook to update status on successful completion
{{ post_hook("
    UPDATE " ~ this ~ "
    SET
        status = 'COMPLETED',
        workforce_snapshot_count = (
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE simulation_year = " ~ var('current_year') ~ "
        ),
        event_count = (
            SELECT COUNT(*) FROM fct_yearly_events
            WHERE simulation_year = " ~ var('current_year') ~ "
        ),
        active_employees = (
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE simulation_year = " ~ var('current_year') ~ "
            AND employee_status = 'ACTIVE'
        ),
        last_updated = CURRENT_TIMESTAMP
    WHERE simulation_year = " ~ var('current_year') ~ "
") }}
```

#### 3. Optimized Core Detection Model
```sql
-- models/intermediate/int_system_state_detection.sql
{{ config(materialized='table') }}

WITH metadata_check AS (
    {{ safe_table_query('int_simulation_metadata',
        [
            {'name': 'last_completed_year', 'default_value': '0'},
            {'name': 'last_status', 'default_value': "'NONE'"},
            {'name': 'total_simulations', 'default_value': '0'}
        ],
        "SELECT
            COALESCE(MAX(CASE WHEN status = 'COMPLETED' THEN simulation_year END), 0) as last_completed_year,
            COALESCE(MAX(status), 'NONE') as last_status,
            COUNT(*) as total_simulations
        FROM int_simulation_metadata"
    ) }}
),
workforce_existence_check AS (
    {{ safe_table_query('fct_workforce_snapshot',
        [
            {'name': 'has_workforce_data', 'default_value': 'false'},
            {'name': 'workforce_count', 'default_value': '0'}
        ],
        "SELECT
            CASE WHEN COUNT(*) > 0 THEN true ELSE false END as has_workforce_data,
            COUNT(*) as workforce_count
        FROM fct_workforce_snapshot
        LIMIT 1"
    ) }}
),
events_existence_check AS (
    {{ safe_table_query('fct_yearly_events',
        [
            {'name': 'has_events_data', 'default_value': 'false'},
            {'name': 'events_count', 'default_value': '0'}
        ],
        "SELECT
            CASE WHEN COUNT(*) > 0 THEN true ELSE false END as has_events_data,
            COUNT(*) as events_count
        FROM fct_yearly_events
        LIMIT 1"
    ) }}
),
census_check AS (
    SELECT
        CASE WHEN COUNT(*) > 0 THEN true ELSE false END as has_census_data,
        COUNT(CASE WHEN termination_date IS NULL THEN 1 END) as active_census_records
    FROM {{ ref('stg_census_data') }}
),
simulation_state AS (
    SELECT
        m.last_completed_year,
        m.last_status,
        m.total_simulations,
        w.has_workforce_data,
        w.workforce_count,
        e.has_events_data,
        e.events_count,
        c.has_census_data,
        c.active_census_records,
        {{ var('current_year') }} as requested_simulation_year
    FROM metadata_check m
    CROSS JOIN workforce_existence_check w
    CROSS JOIN events_existence_check e
    CROSS JOIN census_check c
),
state_classification AS (
    SELECT
        *,
        CASE
            WHEN total_simulations = 0 AND active_census_records > 0 THEN 'COLD_START'
            WHEN requested_simulation_year = 1 THEN 'COLD_START'
            WHEN last_completed_year = requested_simulation_year - 1 THEN 'CONTINUING'
            WHEN last_completed_year < requested_simulation_year - 1 THEN 'INTERRUPTED'
            WHEN last_completed_year >= requested_simulation_year THEN 'ALREADY_COMPLETED'
            WHEN last_status = 'RUNNING' THEN 'CONCURRENT_EXECUTION'
            ELSE 'UNKNOWN'
        END as system_state,
        CASE
            WHEN active_census_records = 0 THEN 'MISSING_CENSUS_DATA'
            WHEN total_simulations = 0 AND active_census_records > 0 THEN 'READY_FOR_INITIALIZATION'
            WHEN has_workforce_data AND has_events_data THEN 'HAS_SIMULATION_DATA'
            ELSE 'PARTIAL_DATA'
        END as data_availability,
        CASE
            WHEN active_census_records = 0 THEN false
            WHEN requested_simulation_year = 1 AND active_census_records > 0 THEN true
            WHEN last_completed_year = requested_simulation_year - 1 AND last_status = 'COMPLETED' THEN true
            WHEN last_status = 'RUNNING' THEN false  -- Prevent concurrent execution
            ELSE false
        END as can_proceed
    FROM simulation_state
)
SELECT
    *,
    CASE
        WHEN NOT can_proceed AND system_state = 'COLD_START' AND data_availability = 'MISSING_CENSUS_DATA'
            THEN 'Cannot proceed: No census data available for initialization'
        WHEN NOT can_proceed AND system_state = 'INTERRUPTED'
            THEN 'Cannot proceed: Missing simulation years between ' || last_completed_year || ' and ' || requested_simulation_year
        WHEN NOT can_proceed AND system_state = 'ALREADY_COMPLETED'
            THEN 'Cannot proceed: Simulation year ' || requested_simulation_year || ' already completed'
        WHEN NOT can_proceed AND system_state = 'CONCURRENT_EXECUTION'
            THEN 'Cannot proceed: Another simulation is currently running'
        WHEN can_proceed
            THEN 'Can proceed with ' || system_state || ' initialization'
        ELSE 'Critical error: Unknown system state requires manual intervention'
    END as recommendation,
    CURRENT_TIMESTAMP as detection_timestamp
FROM state_classification
```

#### 2. Fallback Mechanism Framework
```sql
-- models/intermediate/int_fallback_mechanisms.sql
{{ config(materialized='table') }}

WITH system_state AS (
    SELECT * FROM {{ ref('int_system_state_detection') }}
),
fallback_strategies AS (
    SELECT
        system_state,
        data_availability,
        can_proceed,
        CASE
            WHEN system_state = 'COLD_START' AND data_availability = 'READY_FOR_INITIALIZATION'
                THEN 'USE_CENSUS_BASELINE'
            WHEN system_state = 'CONTINUING' AND data_availability = 'HAS_SIMULATION_DATA'
                THEN 'USE_PREVIOUS_YEAR_DATA'
            WHEN system_state = 'INTERRUPTED'
                THEN 'RECONSTRUCT_FROM_EVENTS'
            WHEN system_state = 'ALREADY_COMPLETED'
                THEN 'SKIP_OR_RERUN'
            ELSE 'NO_FALLBACK_AVAILABLE'
        END as fallback_strategy,
        CASE
            WHEN system_state = 'COLD_START'
                THEN 'SELECT * FROM stg_census_data WHERE termination_date IS NULL'
            WHEN system_state = 'CONTINUING'
                THEN 'SELECT * FROM fct_workforce_snapshot WHERE simulation_year = ' || (requested_simulation_year - 1)
            WHEN system_state = 'INTERRUPTED'
                THEN 'SELECT * FROM fct_yearly_events WHERE simulation_year <= ' || last_simulation_year
            ELSE 'NO_FALLBACK_QUERY'
        END as fallback_query,
        CASE
            WHEN system_state = 'COLD_START' AND active_census_records > 0 THEN 'HIGH'
            WHEN system_state = 'CONTINUING' AND last_simulation_year = requested_simulation_year - 1 THEN 'HIGH'
            WHEN system_state = 'INTERRUPTED' THEN 'MEDIUM'
            ELSE 'LOW'
        END as fallback_confidence
    FROM system_state
)
SELECT * FROM fallback_strategies
```

#### 4. Custom Exception Classes
```python
# orchestrator/exceptions/simulation_exceptions.py
class SimulationError(Exception):
    """Base class for simulation-related errors"""
    pass

class ColdStartError(SimulationError):
    """Raised when cold start initialization fails"""
    pass

class InconsistentStateError(SimulationError):
    """Raised when system state is inconsistent"""
    pass

class MissingDataError(SimulationError):
    """Raised when required data is missing"""
    pass

class InterruptedSimulationError(SimulationError):
    """Raised when simulation is interrupted and requires manual intervention"""
    pass

class ConcurrentExecutionError(SimulationError):
    """Raised when another simulation is already running"""
    pass
```

#### 5. Enhanced Initialization Validation Engine
```python
# orchestrator/utils/initialization_validator.py
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import pandas as pd
from dagster import AssetExecutionContext
from orchestrator.resources import DuckDBResource
from orchestrator.exceptions.simulation_exceptions import (
    ColdStartError, InconsistentStateError, MissingDataError,
    InterruptedSimulationError, ConcurrentExecutionError
)

class SystemState(Enum):
    COLD_START = "COLD_START"
    CONTINUING = "CONTINUING"
    INTERRUPTED = "INTERRUPTED"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    CONCURRENT_EXECUTION = "CONCURRENT_EXECUTION"
    UNKNOWN = "UNKNOWN"

class DataAvailability(Enum):
    MISSING_CENSUS_DATA = "MISSING_CENSUS_DATA"
    READY_FOR_INITIALIZATION = "READY_FOR_INITIALIZATION"
    HAS_SIMULATION_DATA = "HAS_SIMULATION_DATA"
    PARTIAL_DATA = "PARTIAL_DATA"

@dataclass
class SystemStateDetection:
    system_state: SystemState
    data_availability: DataAvailability
    can_proceed: bool
    last_completed_year: int
    requested_simulation_year: int
    active_census_records: int
    has_workforce_data: bool
    has_events_data: bool
    recommendation: str
    fallback_strategy: str
    fallback_confidence: str
    detection_duration_seconds: float

class InitializationValidator:
    """Validates system state and provides fallback mechanisms"""

    def __init__(self, context: AssetExecutionContext, duckdb: DuckDBResource):
        self.context = context
        self.duckdb = duckdb
        self.state_detection: Optional[SystemStateDetection] = None

    def detect_system_state(self, requested_simulation_year: int) -> SystemStateDetection:
        """Detect current system state and determine initialization strategy"""

        import time
        start_time = time.time()

        with self.duckdb.get_connection() as conn:
            # Run state detection query
            detection_result = conn.execute(f"""
                SELECT
                    system_state,
                    data_availability,
                    can_proceed,
                    last_completed_year,
                    requested_simulation_year,
                    active_census_records,
                    has_workforce_data,
                    has_events_data,
                    recommendation
                FROM int_system_state_detection
                WHERE requested_simulation_year = {requested_simulation_year}
            """).fetchone()

            detection_duration = time.time() - start_time

            # Determine fallback strategy based on state
            fallback_strategy, fallback_confidence = self._determine_fallback_strategy(
                detection_result[0], detection_result[1], detection_result[2]
            )

            self.state_detection = SystemStateDetection(
                system_state=SystemState(detection_result[0]),
                data_availability=DataAvailability(detection_result[1]),
                can_proceed=detection_result[2],
                last_completed_year=detection_result[3],
                requested_simulation_year=detection_result[4],
                active_census_records=detection_result[5],
                has_workforce_data=detection_result[6],
                has_events_data=detection_result[7],
                recommendation=detection_result[8],
                fallback_strategy=fallback_strategy,
                fallback_confidence=fallback_confidence,
                detection_duration_seconds=detection_duration
            )

            self.context.log.info(
                f"System state detection ({detection_duration:.3f}s): {self.state_detection.system_state.value} "
                f"(Data: {self.state_detection.data_availability.value}, "
                f"Can proceed: {self.state_detection.can_proceed})"
            )

            return self.state_detection

    def _determine_fallback_strategy(self, system_state: str, data_availability: str, can_proceed: bool) -> Tuple[str, str]:
        """Determine fallback strategy based on detected state"""

        if system_state == 'COLD_START' and data_availability == 'READY_FOR_INITIALIZATION':
            return 'USE_CENSUS_BASELINE', 'HIGH'
        elif system_state == 'CONTINUING' and can_proceed:
            return 'USE_PREVIOUS_YEAR_DATA', 'HIGH'
        elif system_state == 'INTERRUPTED':
            return 'MANUAL_INTERVENTION_REQUIRED', 'LOW'
        elif system_state == 'ALREADY_COMPLETED':
            return 'SKIP_OR_RERUN', 'MEDIUM'
        elif system_state == 'CONCURRENT_EXECUTION':
            return 'WAIT_FOR_COMPLETION', 'LOW'
        else:
            return 'NO_FALLBACK_AVAILABLE', 'NONE'

    def validate_initialization_prerequisites(self) -> Tuple[bool, List[str]]:
        """Validate that all prerequisites for initialization are met"""

        if not self.state_detection:
            return False, ["System state detection not performed"]

        validation_errors = []

        # Check if we can proceed
        if not self.state_detection.can_proceed:
            validation_errors.append(self.state_detection.recommendation)

        # Validate census data availability for cold start
        if (self.state_detection.system_state == SystemState.COLD_START and
            self.state_detection.active_census_records == 0):
            validation_errors.append(
                "Cold start requires active census data, but none found"
            )

        # Validate prior year data for continuing simulation
        if (self.state_detection.system_state == SystemState.CONTINUING and
            self.state_detection.last_completed_year != self.state_detection.requested_simulation_year - 1):
            validation_errors.append(
                f"Continuing simulation requires year {self.state_detection.requested_simulation_year - 1} "
                f"data, but last completed year is {self.state_detection.last_completed_year}"
            )

        # Validate data consistency
        if (self.state_detection.has_workforce_data and not self.state_detection.has_events_data):
            validation_errors.append(
                "Found workforce snapshots but no events - data consistency issue"
            )

        # Handle specific error states
        if self.state_detection.system_state == SystemState.UNKNOWN:
            validation_errors.append(
                "System state is UNKNOWN - this requires immediate manual intervention"
            )

        return len(validation_errors) == 0, validation_errors

    def raise_appropriate_exception(self, validation_errors: List[str]):
        """Raise the most appropriate exception based on validation errors"""

        error_message = "\n".join(validation_errors)

        if not self.state_detection:
            raise InconsistentStateError("System state detection failed")

        if self.state_detection.system_state == SystemState.COLD_START:
            raise ColdStartError(f"Cold start validation failed: {error_message}")
        elif self.state_detection.system_state == SystemState.INTERRUPTED:
            raise InterruptedSimulationError(f"Simulation interrupted: {error_message}")
        elif self.state_detection.system_state == SystemState.CONCURRENT_EXECUTION:
            raise ConcurrentExecutionError(f"Concurrent execution detected: {error_message}")
        elif self.state_detection.system_state == SystemState.UNKNOWN:
            raise InconsistentStateError(f"Unknown system state: {error_message}")
        elif self.state_detection.active_census_records == 0:
            raise MissingDataError(f"Missing census data: {error_message}")
        else:
            raise InconsistentStateError(f"Validation failed: {error_message}")

    def get_fallback_data_source(self) -> Optional[str]:
        """Get the appropriate data source for fallback initialization with explicit columns"""

        if not self.state_detection:
            return None

        fallback_queries = {
            "USE_CENSUS_BASELINE": """
                SELECT
                    employee_id,
                    hire_date,
                    termination_date,
                    annual_salary,
                    job_level,
                    department,
                    'ACTIVE' as employee_status,
                    0 as simulation_year,
                    hire_date as effective_date
                FROM stg_census_data
                WHERE termination_date IS NULL
            """,
            "USE_PREVIOUS_YEAR_DATA": f"""
                SELECT
                    employee_id,
                    hire_date,
                    termination_date,
                    annual_salary,
                    job_level,
                    department,
                    employee_status,
                    simulation_year,
                    effective_date
                FROM fct_workforce_snapshot
                WHERE simulation_year = {self.state_detection.last_completed_year}
            """,
            "MANUAL_INTERVENTION_REQUIRED": None,
            "SKIP_OR_RERUN": None,
            "WAIT_FOR_COMPLETION": None,
            "NO_FALLBACK_AVAILABLE": None
        }

        return fallback_queries.get(self.state_detection.fallback_strategy)

    def execute_fallback_initialization(self) -> pd.DataFrame:
        """Execute fallback initialization based on detected state"""

        fallback_query = self.get_fallback_data_source()

        if not fallback_query:
            raise ValueError(
                f"No fallback available for strategy: {self.state_detection.fallback_strategy}"
            )

        with self.duckdb.get_connection() as conn:
            fallback_data = conn.execute(fallback_query).df()

            self.context.log.info(
                f"Executed fallback initialization with strategy '{self.state_detection.fallback_strategy}': "
                f"{len(fallback_data)} records retrieved"
            )

            return fallback_data

    def log_detection_results(self):
        """Log comprehensive detection results for debugging"""

        if not self.state_detection:
            return

        self.context.log.info("=== System State Detection Results ===")
        self.context.log.info(f"System State: {self.state_detection.system_state.value}")
        self.context.log.info(f"Data Availability: {self.state_detection.data_availability.value}")
        self.context.log.info(f"Can Proceed: {self.state_detection.can_proceed}")
        self.context.log.info(f"Last Simulation Year: {self.state_detection.last_simulation_year}")
        self.context.log.info(f"Requested Year: {self.state_detection.requested_simulation_year}")
        self.context.log.info(f"Active Census Records: {self.state_detection.active_census_records}")
        self.context.log.info(f"Workforce Snapshots: {self.state_detection.workforce_snapshots}")
        self.context.log.info(f"Total Events: {self.state_detection.total_events}")
        self.context.log.info(f"Recommendation: {self.state_detection.recommendation}")
        self.context.log.info(f"Fallback Strategy: {self.state_detection.fallback_strategy}")
        self.context.log.info(f"Fallback Confidence: {self.state_detection.fallback_confidence}")
        self.context.log.info("=====================================")
```

#### 4. Enhanced Asset with State Detection
```python
# orchestrator/assets/workforce_preparation_enhanced.py
from dagster import asset, AssetExecutionContext
from orchestrator.resources import DuckDBResource, DbtResource
from orchestrator.utils.initialization_validator import InitializationValidator
import pandas as pd

@asset(
    deps=["stg_census_data"],
    description="Enhanced workforce preparation with state detection and fallback"
)
def int_baseline_workforce_enhanced(
    context: AssetExecutionContext,
    duckdb: DuckDBResource,
    dbt: DbtResource
) -> pd.DataFrame:
    """Enhanced workforce preparation with intelligent state detection"""

    simulation_year = context.run.run_config.get("simulation_year", 1)

    # Initialize validation framework
    validator = InitializationValidator(context, duckdb)

    # Detect system state
    state_detection = validator.detect_system_state(simulation_year)
    validator.log_detection_results()

    # Validate prerequisites
    can_proceed, validation_errors = validator.validate_initialization_prerequisites()

    if not can_proceed:
        error_message = "Cannot proceed with initialization:\n" + "\n".join(validation_errors)
        context.log.error(error_message)
        raise Exception(error_message)

    # Execute appropriate initialization strategy
    try:
        if state_detection.fallback_strategy == "USE_CENSUS_BASELINE":
            # Cold start initialization
            context.log.info("Executing cold start initialization from census data")
            fallback_data = validator.execute_fallback_initialization()

            # Additional validation for cold start
            if len(fallback_data) == 0:
                raise Exception("Cold start initialization failed: No active employees in census data")

            return fallback_data

        elif state_detection.fallback_strategy == "USE_PREVIOUS_YEAR_DATA":
            # Continuing simulation
            context.log.info("Executing continuing simulation from previous year data")
            fallback_data = validator.execute_fallback_initialization()

            return fallback_data

        elif state_detection.fallback_strategy == "RECONSTRUCT_FROM_EVENTS":
            # Interrupted simulation recovery
            context.log.info("Executing interrupted simulation recovery from events")
            context.log.warning(
                "Reconstruction from events not fully implemented - "
                "consider manual intervention for complex recovery scenarios"
            )

            # For now, fall back to census data
            fallback_data = validator.execute_fallback_initialization()
            return fallback_data

        else:
            raise Exception(f"Unsupported fallback strategy: {state_detection.fallback_strategy}")

    except Exception as e:
        context.log.error(f"Fallback initialization failed: {str(e)}")

        # Try emergency fallback to census data
        if state_detection.active_census_records > 0:
            context.log.warning("Attempting emergency fallback to census data")
            with duckdb.get_connection() as conn:
                emergency_data = conn.execute("""
                    SELECT
                        employee_id,
                        hire_date,
                        termination_date,
                        annual_salary,
                        job_level,
                        department,
                        'ACTIVE' as employee_status,
                        0 as simulation_year
                    FROM stg_census_data
                    WHERE termination_date IS NULL
                """).df()

                if len(emergency_data) > 0:
                    context.log.info(f"Emergency fallback successful: {len(emergency_data)} records")
                    return emergency_data

        # If all fallbacks fail, raise the original exception
        raise e
```

#### 5. Monitoring and Alerting Integration
```python
# orchestrator/utils/state_detection_monitor.py
from typing import Dict, Any
from datetime import datetime
from dagster import AssetExecutionContext
from orchestrator.resources import DuckDBResource
from orchestrator.utils.initialization_validator import SystemStateDetection

class StateDetectionMonitor:
    """Monitor state detection decisions and alert on anomalies"""

    def __init__(self, context: AssetExecutionContext, duckdb: DuckDBResource):
        self.context = context
        self.duckdb = duckdb

    def record_detection_event(self, detection: SystemStateDetection):
        """Record state detection event for monitoring"""

        with self.duckdb.get_connection() as conn:
            conn.execute("""
                INSERT INTO mon_state_detection_events (
                    detection_timestamp,
                    system_state,
                    data_availability,
                    can_proceed,
                    last_simulation_year,
                    requested_simulation_year,
                    active_census_records,
                    workforce_snapshots,
                    total_events,
                    fallback_strategy,
                    fallback_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                datetime.now(),
                detection.system_state.value,
                detection.data_availability.value,
                detection.can_proceed,
                detection.last_simulation_year,
                detection.requested_simulation_year,
                detection.active_census_records,
                detection.workforce_snapshots,
                detection.total_events,
                detection.fallback_strategy,
                detection.fallback_confidence
            ])

    def check_detection_anomalies(self, detection: SystemStateDetection):
        """Check for anomalies in state detection and alert if needed"""

        anomalies = []

        # Check for unexpected state transitions
        if detection.system_state.value == "UNKNOWN":
            anomalies.append("System state could not be determined")

        # Check for data consistency issues
        if detection.workforce_snapshots > 0 and detection.total_events == 0:
            anomalies.append("Workforce snapshots exist but no events found")

        # Check for missing census data
        if detection.active_census_records == 0:
            anomalies.append("No active census records available")

        # Check for simulation year gaps
        if (detection.system_state.value == "CONTINUING" and
            detection.last_simulation_year != detection.requested_simulation_year - 1):
            anomalies.append(
                f"Simulation year gap detected: {detection.last_simulation_year} -> {detection.requested_simulation_year}"
            )

        # Log anomalies
        if anomalies:
            self.context.log.warning(f"State detection anomalies: {', '.join(anomalies)}")

            # Record anomalies for monitoring
            with self.duckdb.get_connection() as conn:
                for anomaly in anomalies:
                    conn.execute("""
                        INSERT INTO mon_state_detection_anomalies (
                            detection_timestamp,
                            anomaly_type,
                            anomaly_description,
                            system_state,
                            severity
                        ) VALUES (?, ?, ?, ?, ?)
                    """, [
                        datetime.now(),
                        "STATE_DETECTION_ANOMALY",
                        anomaly,
                        detection.system_state.value,
                        "HIGH" if "census" in anomaly.lower() else "MEDIUM"
                    ])

        return anomalies
```

---

## Implementation Plan

### Phase 1: Core Detection Framework (2 days)
1. Implement `int_system_state_detection` model
2. Create `InitializationValidator` class
3. Add basic state detection logic
4. Test with various database states

### Phase 2: Fallback Mechanisms (2 days)
1. Implement `int_fallback_mechanisms` model
2. Add fallback execution logic
3. Create emergency fallback procedures
4. Test fallback scenarios

### Phase 3: Integration and Monitoring (1 day)
1. Integrate with workforce preparation assets
2. Add monitoring and alerting
3. Create troubleshooting documentation
4. Validate end-to-end scenarios

---

## Testing Strategy

### State Detection Tests
```python
# tests/test_state_detection.py
def test_cold_start_detection(empty_database):
    """Test cold start detection with empty database"""
    validator = InitializationValidator(context, duckdb)
    detection = validator.detect_system_state(1)

    assert detection.system_state == SystemState.COLD_START
    assert detection.data_availability == DataAvailability.READY_FOR_INITIALIZATION

def test_continuing_simulation_detection(populated_database):
    """Test continuing simulation detection"""
    validator = InitializationValidator(context, duckdb)
    detection = validator.detect_system_state(2)

    assert detection.system_state == SystemState.CONTINUING
    assert detection.can_proceed == True

def test_interrupted_simulation_detection(interrupted_database):
    """Test interrupted simulation detection"""
    validator = InitializationValidator(context, duckdb)
    detection = validator.detect_system_state(5)

    assert detection.system_state == SystemState.INTERRUPTED
    assert detection.can_proceed == False
```

### Fallback Mechanism Tests
```python
# tests/test_fallback_mechanisms.py
def test_census_fallback_execution(duckdb_with_census):
    """Test fallback to census data"""
    validator = InitializationValidator(context, duckdb_with_census)
    detection = validator.detect_system_state(1)

    fallback_data = validator.execute_fallback_initialization()

    assert len(fallback_data) > 0
    assert all(fallback_data['employee_status'] == 'ACTIVE')

def test_previous_year_fallback(duckdb_with_history):
    """Test fallback to previous year data"""
    validator = InitializationValidator(context, duckdb_with_history)
    detection = validator.detect_system_state(3)

    fallback_data = validator.execute_fallback_initialization()

    assert len(fallback_data) > 0
    assert all(fallback_data['simulation_year'] == 2)
```

---

## Performance Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Detection Time | <5 seconds | Time to complete state detection |
| Detection Accuracy | 99.9% | Correct state identification rate |
| Fallback Execution | <30 seconds | Time to execute fallback initialization |
| Memory Usage | <1GB | Memory consumption during detection |

---

## Definition of Done

### Functional Requirements
- [ ] System state detection implemented and tested
- [ ] Fallback mechanisms for all common scenarios
- [ ] Graceful error handling with clear messages
- [ ] Initialization validation with prerequisite checks
- [ ] Emergency fallback procedures for critical failures

### Technical Requirements
- [ ] State detection models deployed
- [ ] InitializationValidator class implemented
- [ ] Monitoring and alerting framework operational
- [ ] Integration with workforce preparation assets
- [ ] Comprehensive logging and debugging support

### Quality Requirements
- [ ] Unit tests for all detection scenarios
- [ ] Integration tests for fallback mechanisms
- [ ] Performance benchmarks met
- [ ] Documentation includes troubleshooting guide
- [ ] Code review completed and approved
