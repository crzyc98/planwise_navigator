# Story S083-04: Multi-Year Performance Monitoring

## Story Overview

**Epic**: E027 - Multi-Year Simulation Reliability & Performance
**Points**: 2
**Priority**: Medium

### User Story
**As an** operations engineer
**I want** comprehensive performance tracking for multi-year runs
**So that** I can detect and resolve performance regressions quickly

### Problem Statement
The current performance monitoring framework lacks specific support for multi-year simulation scenarios. There's no SLA monitoring for long-running SCD operations, no performance regression detection, and limited visibility into multi-year simulation execution patterns.

### Root Cause
The existing performance framework was designed for single-year operations without consideration for the unique challenges of multi-year simulations, such as cumulative performance degradation, memory growth across years, and complex inter-year dependencies.

---

## Acceptance Criteria

### Primary Acceptance Criteria
1. **Multi-Year Metrics**: Extend performance framework to track multi-year simulation metrics
2. **SLA Monitoring**: Add SLA monitoring for long-running SCD operations
3. **Regression Detection**: Create performance regression detection across simulation runs
4. **Trend Analysis**: Track execution time trends across simulation years
5. **Automated Alerting**: Alert on performance degradation patterns

### Secondary Acceptance Criteria
1. **Memory Tracking**: Monitor memory usage growth across simulation years
2. **Dependency Analysis**: Track performance impact of inter-year dependencies
3. **Comparative Analysis**: Compare performance across different simulation scenarios
4. **Dashboard Integration**: Integrate metrics into existing monitoring dashboards

---

## Technical Specifications

### Multi-Year Performance Data Model

#### 1. Enhanced Performance Metrics Schema
```sql
-- Create enhanced performance monitoring tables
CREATE TABLE IF NOT EXISTS mon_multi_year_performance (
    performance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_run_id UUID NOT NULL,
    simulation_year INTEGER NOT NULL,
    component_name VARCHAR(100) NOT NULL,
    component_type VARCHAR(50) NOT NULL, -- 'SCD', 'EVENT_GENERATION', 'WORKFORCE_PREPARATION'
    execution_start_time TIMESTAMP NOT NULL,
    execution_end_time TIMESTAMP NOT NULL,
    execution_time_seconds DECIMAL(10,2) NOT NULL,
    memory_usage_mb DECIMAL(12,2),
    input_record_count BIGINT,
    output_record_count BIGINT,
    records_per_second DECIMAL(10,2),
    sla_threshold_seconds INTEGER,
    sla_status VARCHAR(20), -- 'WITHIN_SLA', 'SLA_WARNING', 'SLA_BREACH'
    performance_category VARCHAR(20), -- 'EXCELLENT', 'GOOD', 'POOR', 'CRITICAL'
    year_over_year_change_pct DECIMAL(5,2),
    cumulative_execution_time_seconds DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mon_multi_year_regression (
    regression_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component_name VARCHAR(100) NOT NULL,
    baseline_run_id UUID NOT NULL,
    current_run_id UUID NOT NULL,
    baseline_execution_time DECIMAL(10,2),
    current_execution_time DECIMAL(10,2),
    performance_degradation_pct DECIMAL(5,2),
    regression_severity VARCHAR(20), -- 'MINOR', 'MAJOR', 'CRITICAL'
    regression_threshold_pct DECIMAL(5,2) DEFAULT 20.0,
    detection_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    investigation_status VARCHAR(50) DEFAULT 'PENDING'
);

CREATE TABLE IF NOT EXISTS mon_sla_definitions (
    sla_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component_name VARCHAR(100) NOT NULL,
    component_type VARCHAR(50) NOT NULL,
    sla_threshold_seconds INTEGER NOT NULL,
    warning_threshold_seconds INTEGER NOT NULL,
    record_count_threshold BIGINT DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. Multi-Year Performance Monitoring Framework
```python
# orchestrator/utils/multi_year_performance_monitor.py
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd
import psutil
from dagster import AssetExecutionContext
from orchestrator.resources import DuckDBResource
import uuid

@dataclass
class PerformanceMetrics:
    component_name: str
    component_type: str
    execution_time_seconds: float
    memory_usage_mb: float
    input_record_count: int
    output_record_count: int
    records_per_second: float
    sla_threshold_seconds: int
    sla_status: str
    performance_category: str

@dataclass
class RegressionAlert:
    component_name: str
    baseline_execution_time: float
    current_execution_time: float
    performance_degradation_pct: float
    regression_severity: str

class MultiYearPerformanceMonitor:
    """Monitor performance across multi-year simulations with SLA tracking"""

    def __init__(self, context: AssetExecutionContext, duckdb: DuckDBResource):
        self.context = context
        self.duckdb = duckdb
        self.simulation_run_id = str(uuid.uuid4())
        self.simulation_year = context.run.run_config.get("simulation_year", 1)
        self.component_metrics: Dict[str, PerformanceMetrics] = {}
        self.process = psutil.Process()

    def initialize_monitoring(self):
        """Initialize performance monitoring for multi-year simulation"""
        with self.duckdb.get_connection() as conn:
            # Ensure SLA definitions exist
            conn.execute("""
                INSERT INTO mon_sla_definitions (component_name, component_type, sla_threshold_seconds, warning_threshold_seconds)
                VALUES
                    ('scd_workforce_state', 'SCD', 120, 90),
                    ('fct_yearly_events', 'EVENT_GENERATION', 300, 240),
                    ('int_baseline_workforce', 'WORKFORCE_PREPARATION', 30, 20),
                    ('multi_year_simulation', 'FULL_SIMULATION', 1800, 1200)
                ON CONFLICT (component_name) DO NOTHING
            """)

        self.context.log.info(f"Initialized multi-year performance monitoring for run {self.simulation_run_id}")

    def start_component_monitoring(self, component_name: str, component_type: str,
                                 input_record_count: int = 0) -> datetime:
        """Start monitoring a specific component"""
        start_time = datetime.now()

        self.context.log.info(f"Started monitoring {component_name} ({component_type})")

        return start_time

    def end_component_monitoring(self, component_name: str, component_type: str,
                               start_time: datetime, output_record_count: int = 0,
                               input_record_count: int = 0) -> PerformanceMetrics:
        """End monitoring and calculate performance metrics"""
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        # Calculate memory usage
        memory_usage_mb = self.process.memory_info().rss / 1024 / 1024

        # Calculate records per second
        records_per_second = output_record_count / execution_time if execution_time > 0 else 0

        # Get SLA threshold
        sla_threshold = self._get_sla_threshold(component_name, component_type)

        # Determine SLA status
        sla_status = self._determine_sla_status(execution_time, sla_threshold)

        # Determine performance category
        performance_category = self._determine_performance_category(
            execution_time, sla_threshold, records_per_second
        )

        metrics = PerformanceMetrics(
            component_name=component_name,
            component_type=component_type,
            execution_time_seconds=execution_time,
            memory_usage_mb=memory_usage_mb,
            input_record_count=input_record_count,
            output_record_count=output_record_count,
            records_per_second=records_per_second,
            sla_threshold_seconds=sla_threshold,
            sla_status=sla_status,
            performance_category=performance_category
        )

        # Store metrics
        self.component_metrics[component_name] = metrics
        self._record_performance_metrics(metrics, start_time, end_time)

        # Check for regressions
        self._check_performance_regression(metrics)

        self.context.log.info(
            f"Completed monitoring {component_name}: {execution_time:.2f}s "
            f"({sla_status}, {performance_category})"
        )

        return metrics

    def _get_sla_threshold(self, component_name: str, component_type: str) -> int:
        """Get SLA threshold for component"""
        with self.duckdb.get_connection() as conn:
            result = conn.execute("""
                SELECT sla_threshold_seconds
                FROM mon_sla_definitions
                WHERE component_name = ? OR component_type = ?
                ORDER BY component_name = ? DESC
                LIMIT 1
            """, [component_name, component_type, component_name]).fetchone()

            return result[0] if result else 300  # Default 5 minutes

    def _determine_sla_status(self, execution_time: float, sla_threshold: int) -> str:
        """Determine SLA status based on execution time"""
        warning_threshold = sla_threshold * 0.8

        if execution_time <= warning_threshold:
            return "WITHIN_SLA"
        elif execution_time <= sla_threshold:
            return "SLA_WARNING"
        else:
            return "SLA_BREACH"

    def _determine_performance_category(self, execution_time: float, sla_threshold: int,
                                      records_per_second: float) -> str:
        """Determine performance category"""
        if execution_time <= sla_threshold * 0.5:
            return "EXCELLENT"
        elif execution_time <= sla_threshold * 0.8:
            return "GOOD"
        elif execution_time <= sla_threshold:
            return "POOR"
        else:
            return "CRITICAL"

    def _record_performance_metrics(self, metrics: PerformanceMetrics,
                                  start_time: datetime, end_time: datetime):
        """Record performance metrics to database"""
        with self.duckdb.get_connection() as conn:
            # Calculate year-over-year change
            yoy_change = self._calculate_year_over_year_change(metrics.component_name,
                                                             metrics.execution_time_seconds)

            # Calculate cumulative execution time
            cumulative_time = self._calculate_cumulative_execution_time(metrics.component_name)

            conn.execute("""
                INSERT INTO mon_multi_year_performance (
                    simulation_run_id,
                    simulation_year,
                    component_name,
                    component_type,
                    execution_start_time,
                    execution_end_time,
                    execution_time_seconds,
                    memory_usage_mb,
                    input_record_count,
                    output_record_count,
                    records_per_second,
                    sla_threshold_seconds,
                    sla_status,
                    performance_category,
                    year_over_year_change_pct,
                    cumulative_execution_time_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                self.simulation_run_id,
                self.simulation_year,
                metrics.component_name,
                metrics.component_type,
                start_time,
                end_time,
                metrics.execution_time_seconds,
                metrics.memory_usage_mb,
                metrics.input_record_count,
                metrics.output_record_count,
                metrics.records_per_second,
                metrics.sla_threshold_seconds,
                metrics.sla_status,
                metrics.performance_category,
                yoy_change,
                cumulative_time
            ])

    def _calculate_year_over_year_change(self, component_name: str,
                                       current_execution_time: float) -> Optional[float]:
        """Calculate year-over-year performance change"""
        if self.simulation_year <= 1:
            return None

        with self.duckdb.get_connection() as conn:
            result = conn.execute("""
                SELECT AVG(execution_time_seconds) as avg_execution_time
                FROM mon_multi_year_performance
                WHERE component_name = ?
                AND simulation_year = ?
                AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            """, [component_name, self.simulation_year - 1]).fetchone()

            if result and result[0]:
                previous_avg = result[0]
                return ((current_execution_time - previous_avg) / previous_avg) * 100

            return None

    def _calculate_cumulative_execution_time(self, component_name: str) -> float:
        """Calculate cumulative execution time across all years"""
        with self.duckdb.get_connection() as conn:
            result = conn.execute("""
                SELECT COALESCE(SUM(execution_time_seconds), 0) as cumulative_time
                FROM mon_multi_year_performance
                WHERE component_name = ?
                AND simulation_run_id = ?
            """, [component_name, self.simulation_run_id]).fetchone()

            return result[0] if result else 0

    def _check_performance_regression(self, metrics: PerformanceMetrics):
        """Check for performance regression and alert if needed"""
        with self.duckdb.get_connection() as conn:
            # Get baseline performance (average of last 5 runs)
            baseline_result = conn.execute("""
                SELECT AVG(execution_time_seconds) as baseline_time
                FROM (
                    SELECT execution_time_seconds
                    FROM mon_multi_year_performance
                    WHERE component_name = ?
                    AND simulation_year = ?
                    AND created_at >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY created_at DESC
                    LIMIT 5
                )
            """, [metrics.component_name, self.simulation_year]).fetchone()

            if baseline_result and baseline_result[0]:
                baseline_time = baseline_result[0]
                degradation_pct = ((metrics.execution_time_seconds - baseline_time) / baseline_time) * 100

                # Check regression thresholds
                if degradation_pct > 50:
                    severity = "CRITICAL"
                elif degradation_pct > 30:
                    severity = "MAJOR"
                elif degradation_pct > 15:
                    severity = "MINOR"
                else:
                    return  # No significant regression

                # Record regression
                conn.execute("""
                    INSERT INTO mon_multi_year_regression (
                        component_name,
                        baseline_run_id,
                        current_run_id,
                        baseline_execution_time,
                        current_execution_time,
                        performance_degradation_pct,
                        regression_severity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [
                    metrics.component_name,
                    "baseline",  # Placeholder for baseline run ID
                    self.simulation_run_id,
                    baseline_time,
                    metrics.execution_time_seconds,
                    degradation_pct,
                    severity
                ])

                # Alert on regression
                self.context.log.warning(
                    f"Performance regression detected for {metrics.component_name}: "
                    f"{degradation_pct:.1f}% degradation ({severity})"
                )

    def generate_performance_summary(self) -> Dict:
        """Generate performance summary for the simulation run"""
        summary = {
            "simulation_run_id": self.simulation_run_id,
            "simulation_year": self.simulation_year,
            "total_components": len(self.component_metrics),
            "total_execution_time": sum(m.execution_time_seconds for m in self.component_metrics.values()),
            "sla_breaches": sum(1 for m in self.component_metrics.values() if m.sla_status == "SLA_BREACH"),
            "performance_issues": sum(1 for m in self.component_metrics.values() if m.performance_category in ["POOR", "CRITICAL"]),
            "components": {name: {
                "execution_time": m.execution_time_seconds,
                "sla_status": m.sla_status,
                "performance_category": m.performance_category,
                "records_per_second": m.records_per_second
            } for name, m in self.component_metrics.items()}
        }

        return summary

    def check_overall_sla_compliance(self) -> bool:
        """Check overall SLA compliance for the simulation run"""
        sla_breaches = sum(1 for m in self.component_metrics.values() if m.sla_status == "SLA_BREACH")

        # Allow up to 1 SLA breach for overall compliance
        return sla_breaches <= 1
```

#### 3. Performance Monitoring Decorators
```python
# orchestrator/utils/performance_decorators.py
from functools import wraps
from typing import Callable, Any
import pandas as pd
from dagster import AssetExecutionContext
from orchestrator.resources import DuckDBResource
from orchestrator.utils.multi_year_performance_monitor import MultiYearPerformanceMonitor

def monitor_performance(component_type: str, track_records: bool = True):
    """Decorator to monitor asset performance"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Extract context and duckdb from args/kwargs
            context = None
            duckdb = None

            for arg in args:
                if isinstance(arg, AssetExecutionContext):
                    context = arg
                elif hasattr(arg, 'get_connection'):
                    duckdb = arg

            if not context or not duckdb:
                # Fallback to normal execution if monitoring not available
                return func(*args, **kwargs)

            # Initialize monitoring
            monitor = MultiYearPerformanceMonitor(context, duckdb)
            component_name = func.__name__

            # Start monitoring
            start_time = monitor.start_component_monitoring(component_name, component_type)

            try:
                # Execute the function
                result = func(*args, **kwargs)

                # Calculate record counts if tracking is enabled
                input_count = 0
                output_count = len(result) if track_records and isinstance(result, pd.DataFrame) else 0

                # End monitoring
                monitor.end_component_monitoring(
                    component_name, component_type, start_time, output_count, input_count
                )

                return result

            except Exception as e:
                # End monitoring even on failure
                monitor.end_component_monitoring(
                    component_name, component_type, start_time, 0, 0
                )
                raise e

        return wrapper
    return decorator

# Usage example
@asset
@monitor_performance("SCD", track_records=True)
def scd_workforce_state(context: AssetExecutionContext, duckdb: DuckDBResource) -> pd.DataFrame:
    """SCD workforce state with automatic performance monitoring"""
    # Asset implementation here
    pass
```

#### 4. Performance Dashboard Integration
```python
# orchestrator/utils/performance_dashboard.py
from typing import Dict, List
import pandas as pd
from dagster import AssetExecutionContext
from orchestrator.resources import DuckDBResource

class PerformanceDashboard:
    """Generate performance dashboard data for multi-year simulations"""

    def __init__(self, duckdb: DuckDBResource):
        self.duckdb = duckdb

    def get_performance_trends(self, days: int = 30) -> pd.DataFrame:
        """Get performance trends over time"""
        with self.duckdb.get_connection() as conn:
            return conn.execute(f"""
                SELECT
                    component_name,
                    simulation_year,
                    DATE_TRUNC('day', created_at) as performance_date,
                    AVG(execution_time_seconds) as avg_execution_time,
                    MAX(execution_time_seconds) as max_execution_time,
                    MIN(execution_time_seconds) as min_execution_time,
                    COUNT(*) as run_count,
                    SUM(CASE WHEN sla_status = 'SLA_BREACH' THEN 1 ELSE 0 END) as sla_breaches
                FROM mon_multi_year_performance
                WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days'
                GROUP BY component_name, simulation_year, DATE_TRUNC('day', created_at)
                ORDER BY performance_date DESC, component_name
            """).df()

    def get_regression_alerts(self, severity: str = None) -> pd.DataFrame:
        """Get recent regression alerts"""
        where_clause = f"WHERE regression_severity = '{severity}'" if severity else ""

        with self.duckdb.get_connection() as conn:
            return conn.execute(f"""
                SELECT
                    component_name,
                    baseline_execution_time,
                    current_execution_time,
                    performance_degradation_pct,
                    regression_severity,
                    detection_timestamp,
                    investigation_status
                FROM mon_multi_year_regression
                {where_clause}
                ORDER BY detection_timestamp DESC
                LIMIT 50
            """).df()

    def get_sla_compliance_summary(self, days: int = 7) -> pd.DataFrame:
        """Get SLA compliance summary"""
        with self.duckdb.get_connection() as conn:
            return conn.execute(f"""
                SELECT
                    component_name,
                    component_type,
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN sla_status = 'WITHIN_SLA' THEN 1 ELSE 0 END) as within_sla,
                    SUM(CASE WHEN sla_status = 'SLA_WARNING' THEN 1 ELSE 0 END) as sla_warnings,
                    SUM(CASE WHEN sla_status = 'SLA_BREACH' THEN 1 ELSE 0 END) as sla_breaches,
                    ROUND(
                        100.0 * SUM(CASE WHEN sla_status = 'WITHIN_SLA' THEN 1 ELSE 0 END) / COUNT(*),
                        2
                    ) as sla_compliance_pct
                FROM mon_multi_year_performance
                WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days'
                GROUP BY component_name, component_type
                ORDER BY sla_compliance_pct ASC
            """).df()
```

---

## Implementation Plan

### Phase 1: Schema and Framework (1 day)
1. Create enhanced performance monitoring tables
2. Implement `MultiYearPerformanceMonitor` class
3. Add SLA definitions and thresholds
4. Test basic monitoring functionality

### Phase 2: Integration and Decorators (1 day)
1. Create performance monitoring decorators
2. Integrate with existing assets
3. Add regression detection logic
4. Create performance dashboard queries

---

## Performance Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Monitoring Overhead | <5% of execution time | Additional time for monitoring |
| Regression Detection | <10 seconds | Time to detect and alert |
| Dashboard Response | <2 seconds | Time to generate dashboard data |
| Storage Efficiency | <100MB per month | Performance data storage |

---

## Definition of Done

### Functional Requirements
- [ ] Multi-year performance metrics collection operational
- [ ] SLA monitoring with alerting implemented
- [ ] Performance regression detection functional
- [ ] Trend analysis and reporting available
- [ ] Dashboard integration completed

### Technical Requirements
- [ ] Performance monitoring tables created
- [ ] MultiYearPerformanceMonitor class implemented
- [ ] Performance decorators deployed
- [ ] Dashboard queries optimized
- [ ] Monitoring overhead minimized

### Quality Requirements
- [ ] Unit tests for monitoring framework
- [ ] Integration tests with real assets
- [ ] Performance impact assessment completed
- [ ] Documentation includes monitoring guide
- [ ] Alerting thresholds validated and tuned
