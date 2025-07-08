# S051: Optimization Monitoring & Observability

**Story Points**: 5
**Priority**: MEDIUM
**Dependencies**: S049 (Optimization Engine Robustness)

## Problem Statement

The optimization engine lacks comprehensive monitoring and audit capabilities required for enterprise deployment:

1. **No Audit Trail**: Parameter changes from optimization aren't logged for SOX compliance
2. **No Performance Metrics**: Can't track optimization efficiency over time
3. **No Failure Analysis**: When optimization fails, root cause is unclear
4. **No Alerting**: Failed optimizations go unnoticed until user complains

## Success Criteria

- [ ] Structured JSON logging for all optimization runs
- [ ] Central audit log with complete parameter change history
- [ ] Performance metrics dashboard (convergence time, iteration count, success rate)
- [ ] Alert system for optimization failures or poor convergence
- [ ] Integration with existing SOW change-log requirements
- [ ] Query interface for historical optimization analysis

## Technical Design

### 1. Structured Logging Framework
```python
import structlog
from datetime import datetime
import json

class OptimizationLogger:
    def __init__(self, log_dir="./logs/optimization"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Configure structured logging
        self.logger = structlog.get_logger()
        self.session_id = str(uuid.uuid4())

    def log_optimization_start(self, config):
        self.logger.info(
            "optimization_started",
            session_id=self.session_id,
            timestamp=datetime.utcnow().isoformat(),
            target_growth=config['target_growth'],
            algorithm=config['algorithm'],
            max_iterations=config['max_iterations'],
            use_synthetic=config.get('use_synthetic', True),
            initial_params=self._get_current_params(),
            user=os.getenv('USER', 'unknown')
        )

    def log_iteration(self, iteration, params, objective_value, gradient=None):
        self.logger.info(
            "optimization_iteration",
            session_id=self.session_id,
            iteration=iteration,
            params={
                'cola': params[0],
                'merit_avg': params[1],
                'hire_adj': params[2]
            },
            objective_value=objective_value,
            gradient=gradient,
            timestamp=datetime.utcnow().isoformat()
        )

    def log_optimization_complete(self, result):
        self.logger.info(
            "optimization_completed",
            session_id=self.session_id,
            converged=result['converged'],
            final_objective=result['objective_value'],
            iterations_used=result['iterations'],
            final_params=result['final_params'],
            duration_seconds=result.get('duration'),
            timestamp=datetime.utcnow().isoformat()
        )
```

### 2. Central Audit Log
```python
class ParameterAuditLog:
    """SOX-compliant parameter change tracking"""

    def __init__(self, db_path="./audit/parameter_changes.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create audit tables if not exist"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parameter_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                user TEXT,
                parameter_name TEXT,
                job_level INTEGER,
                fiscal_year INTEGER,
                old_value REAL,
                new_value REAL,
                change_source TEXT,  -- 'optimization', 'manual', 'import'
                optimization_target REAL,
                approved_by TEXT,
                approval_timestamp DATETIME
            )
        """)
        conn.close()

    def log_parameter_change(self, change_data):
        """Log a parameter change with full context"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO parameter_changes
            (session_id, user, parameter_name, job_level, fiscal_year,
             old_value, new_value, change_source, optimization_target)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            change_data['session_id'],
            change_data['user'],
            change_data['parameter_name'],
            change_data['job_level'],
            change_data['fiscal_year'],
            change_data['old_value'],
            change_data['new_value'],
            change_data['change_source'],
            change_data.get('optimization_target')
        ))
        conn.commit()
        conn.close()
```

### 3. Performance Metrics Dashboard
```python
class OptimizationMetrics:
    def __init__(self):
        self.metrics_store = MetricsStore()

    def calculate_metrics(self, time_window='7d'):
        """Calculate key performance indicators"""
        runs = self.metrics_store.get_runs(time_window)

        return {
            'total_runs': len(runs),
            'success_rate': sum(r['converged'] for r in runs) / len(runs),
            'avg_iterations': np.mean([r['iterations'] for r in runs]),
            'avg_convergence_time': np.mean([r['duration'] for r in runs if r['converged']]),
            'failure_reasons': self._analyze_failures(runs),
            'algorithm_performance': self._compare_algorithms(runs),
            'parameter_drift': self._analyze_parameter_trends(runs)
        }

    def create_dashboard(self):
        """Streamlit dashboard for optimization metrics"""
        st.title("🎯 Optimization Performance Dashboard")

        # Time window selector
        window = st.selectbox("Time Window", ["24h", "7d", "30d", "90d"])
        metrics = self.calculate_metrics(window)

        # KPI Cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Success Rate", f"{metrics['success_rate']:.1%}",
                     delta=f"{metrics['success_rate_change']:+.1%}")
        with col2:
            st.metric("Avg Iterations", f"{metrics['avg_iterations']:.1f}",
                     help="Lower is better")
        with col3:
            st.metric("Avg Time (min)", f"{metrics['avg_convergence_time']/60:.1f}")
        with col4:
            st.metric("Total Runs", metrics['total_runs'])

        # Failure Analysis
        if metrics['failure_reasons']:
            st.subheader("⚠️ Failure Analysis")
            failure_df = pd.DataFrame(metrics['failure_reasons'])
            st.bar_chart(failure_df.set_index('reason')['count'])
```

### 4. Alert System
```python
class OptimizationAlerts:
    def __init__(self, alert_config):
        self.config = alert_config
        self.alert_channels = self._setup_channels()

    def check_alerts(self, optimization_result):
        """Check if result triggers any alerts"""
        alerts = []

        # Failed optimization
        if not optimization_result['converged']:
            alerts.append({
                'level': 'error',
                'message': f"Optimization failed to converge after {optimization_result['iterations']} iterations",
                'details': optimization_result
            })

        # Poor convergence
        elif optimization_result['iterations'] > self.config['max_iterations_warning']:
            alerts.append({
                'level': 'warning',
                'message': f"Optimization took {optimization_result['iterations']} iterations (threshold: {self.config['max_iterations_warning']})",
                'details': optimization_result
            })

        # Extreme parameter values
        final_params = optimization_result['final_params']
        if final_params['cola_rate'] > 0.07:  # >7% COLA
            alerts.append({
                'level': 'warning',
                'message': f"High COLA rate: {final_params['cola_rate']:.1%}",
                'details': final_params
            })

        return alerts

    def send_alerts(self, alerts):
        """Route alerts to configured channels"""
        for alert in alerts:
            if alert['level'] == 'error':
                self._send_email(alert)
                self._send_slack(alert)
            elif alert['level'] == 'warning':
                self._log_warning(alert)
```

### 5. Query Interface
```python
class OptimizationQueryInterface:
    """SQL-like interface for optimization history"""

    def query(self, sql):
        """Execute SQL query on optimization logs"""
        # Convert JSON logs to queryable format
        df = self._load_logs_to_dataframe()

        # Register with DuckDB for SQL queries
        conn = duckdb.connect(':memory:')
        conn.register('optimizations', df)

        result = conn.execute(sql).fetchdf()
        conn.close()

        return result

    def common_queries(self):
        return {
            'failed_runs_last_week': """
                SELECT session_id, timestamp, target_growth, iterations
                FROM optimizations
                WHERE converged = false
                AND timestamp > current_date - interval '7 days'
                ORDER BY timestamp DESC
            """,

            'parameter_trends': """
                SELECT
                    date_trunc('day', timestamp) as day,
                    avg(final_cola) as avg_cola,
                    avg(final_merit) as avg_merit
                FROM optimizations
                WHERE converged = true
                GROUP BY day
                ORDER BY day
            """,

            'algorithm_comparison': """
                SELECT
                    algorithm,
                    count(*) as runs,
                    avg(CASE WHEN converged THEN 1 ELSE 0 END) as success_rate,
                    avg(iterations) as avg_iterations
                FROM optimizations
                GROUP BY algorithm
            """
        }
```

## Integration Points

1. **SOW Change Log**: Push parameter changes to central change management system
2. **Monitoring Stack**: Export metrics to Prometheus/Grafana
3. **Data Lake**: Stream logs to S3/Azure for long-term analysis
4. **Compliance**: Generate SOX audit reports on demand

## Testing Requirements

- Test log rotation doesn't lose data
- Test alerts fire correctly for various failure modes
- Test query performance on 1M+ log entries
- Test audit log maintains referential integrity

## Implementation Notes

1. **Log Retention**: 90 days hot storage, archive to S3 thereafter
2. **Alert Throttling**: Max 1 alert per failure type per hour
3. **Dashboard Caching**: Metrics refresh every 5 minutes
4. **Query Limits**: Max 10k rows per query for performance

## Definition of Done

- [ ] Structured logging implemented for all optimization paths
- [ ] Audit log captures all parameter changes
- [ ] Dashboard shows real-time metrics
- [ ] Alert system configured and tested
- [ ] Query interface supports common analysis patterns
- [ ] Documentation includes troubleshooting guide
