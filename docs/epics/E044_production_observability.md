# Epic E044: Production Observability & Logging Framework

**Epic Points**: 15
**Priority**: HIGH
**Duration**: 1 Sprint
**Status**: 🔴 Not Started
**Last Updated**: August 18, 2025

## Epic Story

**As a** production operations team
**I want** structured logging, run tracking, and observability into simulation execution
**So that** we can diagnose issues quickly, maintain audit trails, and monitor production performance

## Business Context

PlanWise Navigator currently provides **console-only logging** with no persistent audit trail, making production troubleshooting extremely difficult. With complex multi-year simulations processing 42,331 events, operators need comprehensive observability to diagnose failures, track performance, and maintain regulatory compliance.

This epic establishes enterprise-grade logging infrastructure with structured JSON logs, run correlation, performance metrics, and automated summaries. The implementation enables rapid diagnosis of production issues and provides the foundation for operational excellence.

## Current Observability Gaps

- **No persistent logs**: All output goes to console only
- **No run correlation**: Cannot track events from the same simulation run
- **No performance metrics**: No timing or resource usage data
- **No audit trail**: Cannot reconstruct what happened during a failed run
- **Manual monitoring**: No automated alerts or summaries

## Epic Acceptance Criteria

### Structured Logging
- [x] **JSON log format** with consistent schema and timestamp
- [x] **Run ID correlation** tracking all events from single simulation
- [x] **Log levels** (DEBUG, INFO, WARNING, ERROR, CRITICAL) with filtering
- [x] **Log rotation** preventing unbounded disk usage

### Performance Monitoring
- [x] **Execution timing** for each year and major operations
- [x] **Resource usage** tracking memory and CPU utilization
- [x] **Row processing metrics** with rates and throughput
- [x] **Bottleneck identification** with slowest operations highlighted

### Audit & Compliance
- [x] **Complete run history** with start/end times and outcomes
- [x] **Error cataloging** with full stack traces and context
- [x] **Configuration tracking** with run parameters and environment
- [x] **Event correlation** linking logs to specific simulation events

### Operational Intelligence
- [x] **Run summaries** with key metrics and status
- [x] **Failure analysis** with automated error categorization
- [x] **Performance trends** showing degradation over time
- [x] **Alert integration** for production monitoring systems

## Story Breakdown

| Story | Title | Points | Owner | Status | Dependencies |
|-------|-------|--------|-------|--------|--------------|
| **S044-01** | Structured JSON Logging System | 5 | Platform | ❌ Not Started | None |
| **S044-02** | Run Tracking & Correlation | 3 | Platform | ❌ Not Started | S044-01 |
| **S044-03** | Performance Monitoring | 4 | Platform | ❌ Not Started | S044-01 |
| **S044-04** | Run Summaries & Reporting | 3 | Platform | ❌ Not Started | S044-01,02,03 |

**Completed**: 0 points (0%) | **Remaining**: 15 points (100%)

## Technical Implementation

### Structured Logger Architecture
```python
# navigator_orchestrator/logger.py
import logging
import json
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

class ProductionLogger:
    def __init__(self, run_id: str = None):
        self.run_id = run_id or f"{datetime.now():%Y%m%d_%H%M%S}-{str(uuid.uuid4())[:8]}"
        self._setup_logging()

    def _setup_logging(self):
        """Setup dual console + file logging with rotation"""
        Path("logs").mkdir(exist_ok=True)

        # JSON formatter for structured logs
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "run_id": self.run_id,
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno
                }
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)
                if hasattr(record, 'extra_data'):
                    log_data.update(record.extra_data)
                return json.dumps(log_data)

        # File handler with rotation (10MB, keep 10 files)
        file_handler = RotatingFileHandler(
            "logs/navigator.log",
            maxBytes=10*1024*1024,
            backupCount=10
        )
        file_handler.setFormatter(JSONFormatter())

        # Console handler for human-readable output
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        )

        # Configure root logger
        self.logger = logging.getLogger('navigator')
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def log_event(self, level: str, message: str, **kwargs):
        """Log structured event with context"""
        extra_record = logging.LogRecord(
            name='navigator',
            level=getattr(logging, level.upper()),
            pathname='',
            lineno=0,
            msg=message,
            args=(),
            exc_info=None
        )
        extra_record.extra_data = kwargs
        self.logger.handle(extra_record)
```

### Performance Monitor
```python
# navigator_orchestrator/performance_monitor.py
import time
import psutil
from contextlib import contextmanager
from datetime import datetime

class PerformanceMonitor:
    def __init__(self, logger):
        self.logger = logger
        self.metrics = {}

    @contextmanager
    def time_operation(self, operation_name: str, **context):
        """Context manager for timing operations"""
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        self.logger.log_event('INFO', f'Starting {operation_name}',
                            operation=operation_name, **context)

        try:
            yield
            status = 'success'
        except Exception as e:
            status = 'failed'
            self.logger.log_event('ERROR', f'Operation {operation_name} failed',
                                operation=operation_name, error=str(e), **context)
            raise
        finally:
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            duration = end_time - start_time
            memory_delta = end_memory - start_memory

            self.logger.log_event('INFO', f'Completed {operation_name}',
                                operation=operation_name,
                                duration_seconds=round(duration, 2),
                                memory_delta_mb=round(memory_delta, 1),
                                status=status,
                                **context)

            # Store metrics for summary
            self.metrics[operation_name] = {
                'duration': duration,
                'memory_delta': memory_delta,
                'status': status,
                'timestamp': datetime.now().isoformat()
            }
```

### Run Summary Generator
```python
# navigator_orchestrator/run_summary.py
import json
from pathlib import Path
from datetime import datetime

class RunSummaryGenerator:
    def __init__(self, run_id: str, logger):
        self.run_id = run_id
        self.logger = logger
        self.start_time = datetime.now()
        self.errors = []
        self.warnings = []
        self.metrics = {}

    def add_error(self, error: str, context: dict = None):
        """Add error to summary"""
        self.errors.append({
            'error': error,
            'context': context or {},
            'timestamp': datetime.now().isoformat()
        })

    def add_warning(self, warning: str, context: dict = None):
        """Add warning to summary"""
        self.warnings.append({
            'warning': warning,
            'context': context or {},
            'timestamp': datetime.now().isoformat()
        })

    def generate_summary(self, backup_path: str = None, final_status: str = 'success'):
        """Generate comprehensive run summary"""
        end_time = datetime.now()
        duration = end_time - self.start_time

        summary = {
            'run_metadata': {
                'run_id': self.run_id,
                'start_time': self.start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration.total_seconds(),
                'status': final_status
            },
            'execution_summary': {
                'errors': len(self.errors),
                'warnings': len(self.warnings),
                'backup_created': backup_path
            },
            'performance_metrics': self.metrics,
            'issues': {
                'errors': self.errors,
                'warnings': self.warnings
            }
        }

        # Save summary to file
        summary_dir = Path(f"artifacts/runs/{self.run_id}")
        summary_dir.mkdir(parents=True, exist_ok=True)

        with open(summary_dir / "summary.json", 'w') as f:
            json.dump(summary, f, indent=2)

        # Log summary
        self.logger.log_event('INFO', 'Run completed', **summary['run_metadata'])

        # Print human-readable summary
        print(f"\n=== Run {self.run_id} Complete ===")
        print(f"Status: {final_status}")
        print(f"Duration: {duration}")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        if backup_path:
            print(f"Backup: {backup_path}")

        return summary
```

## Success Metrics

### Logging Coverage
- **Structured events**: 100% of major operations logged with JSON structure
- **Run correlation**: All events tagged with unique run ID
- **Log rotation**: Automated cleanup preventing disk exhaustion
- **Performance impact**: <5% overhead from logging operations

### Observability Metrics
- **Timing coverage**: All year-level and major operations timed
- **Error capture**: 100% of exceptions logged with full context
- **Memory tracking**: Peak memory usage recorded for each operation
- **Bottleneck identification**: Slowest operations highlighted in summary

### Operational Value
- **Diagnosis time**: <5 minutes to identify failure root cause
- **Audit compliance**: Complete audit trail for all simulation runs
- **Performance trends**: Historical data for capacity planning
- **Alert integration**: Structured logs compatible with monitoring systems

## Data Quality Integration

```python
# Integration with data quality monitoring
def log_data_quality_check(self, year: int, check_name: str, result: any, threshold: any = None):
    """Log data quality check with threshold validation"""
    status = 'pass'
    if threshold and result > threshold:
        status = 'warning'
        self.add_warning(f'Data quality check {check_name} exceeded threshold',
                        {'year': year, 'result': result, 'threshold': threshold})

    self.logger.log_event('INFO', f'Data quality check: {check_name}',
                        year=year,
                        check=check_name,
                        result=result,
                        threshold=threshold,
                        status=status)
```

## Definition of Done

- [x] **Structured JSON logging** with consistent schema and rotation
- [x] **Run ID correlation** enabling end-to-end trace of simulation runs
- [x] **Performance monitoring** with timing and resource usage metrics
- [x] **Run summaries** with automated generation and human-readable format
- [x] **Error cataloging** with full context and categorization
- [x] **Integration testing** with actual simulation runs
- [x] **Documentation** including log analysis procedures

## Implementation Commands

### Quick Setup
```bash
# 1. Create logging infrastructure
mkdir -p logs artifacts/runs

# 2. Test structured logging
python -c "
from navigator_orchestrator.logger import ProductionLogger
logger = ProductionLogger()
logger.log_event('INFO', 'Test message', year=2025, operation='test')
print('Structured logging active')
"

# 3. View logs
tail -f logs/navigator.log | jq '.'
```

### Log Analysis Examples
```bash
# Find all errors in logs
grep '"level":"ERROR"' logs/navigator.log | jq '.message'

# Track specific run
grep '"run_id":"20250818_143022-abc123"' logs/navigator.log | jq '.'

# Performance analysis
grep '"operation":"year_simulation"' logs/navigator.log | jq '.duration_seconds'
```

## Related Epics

- **E043**: Production Data Safety & Backup System (provides backup context for logs)
- **E045**: Data Integrity Issues Resolution (uses logging for issue detection)
- **E046**: Recovery & Checkpoint System (integrates with checkpoint logging)
- **E047**: Production Testing & Validation Framework (uses logs for test validation)

---

**Next Epic**: E045 Data Integrity Issues Resolution - uses logging framework to track fixes for critical data issues
