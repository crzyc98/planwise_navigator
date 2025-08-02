# orchestrator_dbt Troubleshooting Guide

**Version:** 1.0.0
**Package:** `orchestrator_dbt`
**Target Performance:** 82% improvement over legacy MVP

A comprehensive troubleshooting guide for resolving common issues with the optimized orchestrator_dbt package and achieving optimal performance in production environments.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Performance Issues](#performance-issues)
- [Configuration Problems](#configuration-problems)
- [Memory and Resource Issues](#memory-and-resource-issues)
- [Database and Connectivity Issues](#database-and-connectivity-issues)
- [Integration Problems](#integration-problems)
- [Error Messages and Solutions](#error-messages-and-solutions)
- [Performance Tuning](#performance-tuning)
- [Best Practices](#best-practices)
- [Production Deployment](#production-deployment)

## Quick Diagnostics

### Health Check Command

Run a quick health check to diagnose common issues:

```bash
# Basic health check
python -m orchestrator_dbt.run_multi_year --test-config --verbose

# Foundation setup performance test
python -m orchestrator_dbt.run_multi_year --foundation-only --benchmark --verbose

# Configuration compatibility test
python -m orchestrator_dbt.run_multi_year --test-config --config /path/to/simulation_config.yaml
```

### System Requirements Check

Verify your system meets the minimum requirements:

```python
import psutil
import sys
from pathlib import Path

def system_check():
    """Perform basic system requirements check."""
    print("🔍 System Requirements Check")
    print("=" * 40)

    # Python version
    python_version = sys.version_info
    print(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version < (3, 11):
        print("⚠️  WARNING: Python 3.11+ recommended")
    else:
        print("✅ Python version OK")

    # Memory
    memory_gb = psutil.virtual_memory().total / (1024**3)
    print(f"Total memory: {memory_gb:.1f} GB")
    if memory_gb < 4:
        print("⚠️  WARNING: 4GB+ memory recommended")
    else:
        print("✅ Memory OK")

    # Disk space
    disk_usage = psutil.disk_usage('.')
    free_gb = disk_usage.free / (1024**3)
    print(f"Free disk space: {free_gb:.1f} GB")
    if free_gb < 2:
        print("⚠️  WARNING: 2GB+ free space recommended")
    else:
        print("✅ Disk space OK")

    # CPU cores
    cpu_count = psutil.cpu_count()
    print(f"CPU cores: {cpu_count}")
    if cpu_count < 2:
        print("⚠️  WARNING: 2+ CPU cores recommended")
    else:
        print("✅ CPU cores OK")

system_check()
```

## Performance Issues

### Issue: Foundation Setup > 10 Second Target

**Symptoms:**
- Foundation setup takes longer than 10 seconds
- Performance improvement target not met
- Slow initial startup

**Diagnostics:**
```bash
python -m orchestrator_dbt.run_multi_year --foundation-only --benchmark --verbose
```

**Solutions:**

1. **Reduce Batch Size**
   ```bash
   python -m orchestrator_dbt.run_multi_year --foundation-only --batch-size 500
   ```

2. **Lower Optimization Level**
   ```bash
   python -m orchestrator_dbt.run_multi_year --foundation-only --optimization medium
   ```

3. **Check System Resources**
   ```python
   import psutil

   # Check CPU usage
   cpu_percent = psutil.cpu_percent(interval=1)
   print(f"CPU usage: {cpu_percent}%")

   # Check memory usage
   memory = psutil.virtual_memory()
   print(f"Memory usage: {memory.percent}%")

   # Check disk I/O
   disk_io = psutil.disk_io_counters()
   print(f"Disk read: {disk_io.read_bytes / (1024**2):.1f}MB")
   print(f"Disk write: {disk_io.write_bytes / (1024**2):.1f}MB")
   ```

4. **Database Optimization**
   ```bash
   # Check if database file is locked
   lsof simulation.duckdb

   # Verify database file permissions
   ls -la simulation.duckdb
   ```

### Issue: Multi-Year Simulation Performance Degradation

**Symptoms:**
- Simulation slows down over multiple years
- Memory usage increases significantly
- Processing rate decreases

**Solutions:**

1. **Enable State Compression**
   ```bash
   python -m orchestrator_dbt.run_multi_year --enable-compression --start-year 2025 --end-year 2029
   ```

2. **Optimize Worker Configuration**
   ```bash
   # For CPU-bound workloads
   python -m orchestrator_dbt.run_multi_year --max-workers 8 --batch-size 2000

   # For memory-constrained environments
   python -m orchestrator_dbt.run_multi_year --max-workers 2 --batch-size 500
   ```

3. **Monitor Memory Usage**
   ```python
   from orchestrator_dbt.run_multi_year import PerformanceMonitor

   monitor = PerformanceMonitor()
   monitor.start()

   # ... run simulation ...

   summary = monitor.get_summary()
   print(f"Peak memory: {summary['peak_memory_mb']:.1f}MB")
   print(f"Memory efficiency: {summary['memory_efficiency']:.1%}")
   ```

### Issue: 82% Performance Improvement Target Not Met

**Symptoms:**
- Performance comparison shows < 82% improvement
- Regression tests fail
- Slower than expected execution

**Diagnostics:**
```bash
python -m orchestrator_dbt.run_multi_year --compare-mvp --start-year 2025 --end-year 2027 --benchmark
```

**Solutions:**

1. **Verify MVP Baseline**
   ```python
   # Check if MVP orchestrator is available
   try:
       from orchestrator_mvp.core.multi_year_orchestrator import MultiYearSimulationOrchestrator
       print("✅ MVP orchestrator available")
   except ImportError:
       print("❌ MVP orchestrator not available for comparison")
   ```

2. **Optimize Configuration**
   ```bash
   # High-performance configuration
   python -m orchestrator_dbt.run_multi_year \
       --optimization high \
       --max-workers 8 \
       --batch-size 2000 \
       --enable-compression \
       --performance-mode
   ```

3. **System Performance Baseline**
   ```bash
   # Run system performance test
   python -c "
   import time
   start = time.time()
   sum(range(10000000))
   print(f'CPU baseline: {time.time() - start:.2f}s')
   "
   ```

## Configuration Problems

### Issue: Configuration Validation Failures

**Symptoms:**
- "Invalid configuration" errors
- Missing required fields
- Value range errors

**Common Errors and Solutions:**

1. **Missing Required Sections**
   ```yaml
   # ❌ Invalid - missing workforce section
   simulation:
     start_year: 2025
     end_year: 2027
     target_growth_rate: 0.03
   random_seed: 42

   # ✅ Valid - all required sections present
   simulation:
     start_year: 2025
     end_year: 2027
     target_growth_rate: 0.03
   workforce:
     total_termination_rate: 0.12
   random_seed: 42
   ```

2. **Invalid Value Ranges**
   ```yaml
   # ❌ Invalid - rates must be 0.0-1.0
   workforce:
     total_termination_rate: 1.5  # > 1.0

   # ✅ Valid
   workforce:
     total_termination_rate: 0.15  # 0.0-1.0
   ```

3. **Invalid Year Ranges**
   ```yaml
   # ❌ Invalid - end_year must be > start_year
   simulation:
     start_year: 2027
     end_year: 2025

   # ✅ Valid
   simulation:
     start_year: 2025
     end_year: 2027
   ```

### Issue: Configuration Compatibility Problems

**Symptoms:**
- Legacy system incompatibility
- Migration issues from MVP
- Configuration format errors

**Diagnostics:**
```bash
python -m orchestrator_dbt.run_multi_year --test-config --config /path/to/config.yaml --verbose
```

**Solutions:**

1. **Legacy Configuration Migration**
   ```python
   # Convert legacy format to new format
   def migrate_legacy_config(legacy_config):
       """Migrate legacy configuration format."""
       new_config = {
           'simulation': {
               'start_year': legacy_config['start_year'],
               'end_year': legacy_config['end_year'],
               'target_growth_rate': legacy_config['target_growth_rate']
           },
           'workforce': {
               'total_termination_rate': legacy_config['workforce']['total_termination_rate']
           },
           'random_seed': legacy_config.get('random_seed', 42)
       }

       # Add optional sections if present
       if 'eligibility' in legacy_config:
           new_config['eligibility'] = legacy_config['eligibility']

       if 'enrollment' in legacy_config:
           new_config['enrollment'] = legacy_config['enrollment']

       return new_config
   ```

2. **Configuration Validation Script**
   ```python
   from orchestrator_dbt.run_multi_year import validate_configuration, load_and_validate_config

   def validate_config_file(config_path):
       """Validate configuration file and provide detailed feedback."""
       try:
           config = load_and_validate_config(config_path)
           is_valid, errors = validate_configuration(config)

           if is_valid:
               print("✅ Configuration is valid")
           else:
               print("❌ Configuration validation failed:")
               for error in errors:
                   print(f"   • {error}")

           return is_valid

       except Exception as e:
           print(f"❌ Configuration loading failed: {e}")
           return False
   ```

## Memory and Resource Issues

### Issue: Out of Memory Errors

**Symptoms:**
- `MemoryError` exceptions
- System becomes unresponsive
- Process killed by OS

**Solutions:**

1. **Enable Compression**
   ```bash
   python -m orchestrator_dbt.run_multi_year --enable-compression
   ```

2. **Reduce Batch Size**
   ```bash
   python -m orchestrator_dbt.run_multi_year --batch-size 500
   ```

3. **Limit Worker Threads**
   ```bash
   python -m orchestrator_dbt.run_multi_year --max-workers 2
   ```

4. **Monitor Memory Usage**
   ```python
   import psutil
   import os

   process = psutil.Process(os.getpid())

   def log_memory_usage():
       memory_info = process.memory_info()
       memory_mb = memory_info.rss / (1024 * 1024)
       print(f"Memory usage: {memory_mb:.1f}MB")

   # Call periodically during simulation
   log_memory_usage()
   ```

### Issue: High CPU Usage

**Symptoms:**
- CPU usage at 100%
- System becomes slow
- Thermal throttling

**Solutions:**

1. **Reduce Worker Threads**
   ```bash
   python -m orchestrator_dbt.run_multi_year --max-workers 4  # Adjust based on CPU cores
   ```

2. **Use Lower Optimization Level**
   ```bash
   python -m orchestrator_dbt.run_multi_year --optimization medium
   ```

3. **Add Processing Delays**
   ```python
   import asyncio

   # Add small delays in processing loops
   async def controlled_processing():
       for item in processing_queue:
           process_item(item)
           await asyncio.sleep(0.001)  # Small delay to prevent CPU saturation
   ```

### Issue: Disk Space Issues

**Symptoms:**
- "No space left on device" errors
- Database write failures
- Log file growth

**Solutions:**

1. **Check Disk Usage**
   ```bash
   df -h .
   du -sh simulation.duckdb
   du -sh logs/
   ```

2. **Clean Up Old Files**
   ```bash
   # Remove old log files
   find logs/ -name "*.log" -mtime +7 -delete

   # Compress old database files
   gzip old_simulation_*.duckdb
   ```

3. **Configure Log Rotation**
   ```python
   import logging
   from logging.handlers import RotatingFileHandler

   # Configure rotating log handler
   handler = RotatingFileHandler(
       'logs/simulation.log',
       maxBytes=10*1024*1024,  # 10MB
       backupCount=5
   )
   logging.getLogger().addHandler(handler)
   ```

## Database and Connectivity Issues

### Issue: Database Connection Errors

**Symptoms:**
- "Database is locked" errors
- Connection timeout errors
- File access permissions

**Solutions:**

1. **Check Database Locks**
   ```bash
   # Check if database is locked by another process
   lsof simulation.duckdb
   fuser simulation.duckdb
   ```

2. **Verify Permissions**
   ```bash
   ls -la simulation.duckdb
   chmod 644 simulation.duckdb  # If needed
   ```

3. **Close IDE Connections**
   - Close any database connections in VS Code, Windsurf, or other IDEs
   - Exit database viewers or query tools

4. **Database Recovery**
   ```python
   import duckdb

   def recover_database():
       """Attempt database recovery."""
       try:
           # Try to connect and run simple query
           conn = duckdb.connect('simulation.duckdb')
           result = conn.execute("SELECT COUNT(*) FROM information_schema.tables").fetchone()
           print(f"Database accessible: {result[0]} tables found")
           conn.close()
           return True
       except Exception as e:
           print(f"Database recovery needed: {e}")
           return False
   ```

### Issue: DuckDB Extension Problems

**Symptoms:**
- Extension loading failures
- Missing functionality
- Version compatibility issues

**Solutions:**

1. **Install Required Extensions**
   ```python
   import duckdb

   conn = duckdb.connect()

   # Install commonly needed extensions
   extensions = ['httpfs', 'parquet', 'json']
   for ext in extensions:
       try:
           conn.execute(f"INSTALL {ext}")
           conn.execute(f"LOAD {ext}")
           print(f"✅ Extension {ext} loaded")
       except Exception as e:
           print(f"❌ Extension {ext} failed: {e}")

   conn.close()
   ```

2. **Version Compatibility Check**
   ```python
   import duckdb

   print(f"DuckDB version: {duckdb.__version__}")

   # Check if version is compatible
   version_parts = duckdb.__version__.split('.')
   major, minor = int(version_parts[0]), int(version_parts[1])

   if major >= 1 and minor >= 0:
       print("✅ DuckDB version compatible")
   else:
       print("⚠️  DuckDB version may have compatibility issues")
   ```

## Integration Problems

### Issue: MVP Orchestrator Integration

**Symptoms:**
- MVP comparison fails
- Import errors for legacy components
- Configuration format mismatches

**Solutions:**

1. **Check MVP Availability**
   ```python
   def check_mvp_availability():
       """Check if MVP orchestrator is available."""
       try:
           from orchestrator_mvp.core.multi_year_orchestrator import MultiYearSimulationOrchestrator
           print("✅ MVP orchestrator available")
           return True
       except ImportError as e:
           print(f"❌ MVP orchestrator not available: {e}")
           print("Performance comparison will be skipped")
           return False

   check_mvp_availability()
   ```

2. **Configuration Format Conversion**
   ```python
   def convert_config_for_mvp(new_config):
       """Convert new configuration format for MVP compatibility."""
       mvp_config = {
           'target_growth_rate': new_config['simulation']['target_growth_rate'],
           'workforce': new_config['workforce'],
           'random_seed': new_config.get('random_seed', 42)
       }

       # Add optional sections
       for section in ['eligibility', 'enrollment', 'compensation']:
           if section in new_config:
               mvp_config[section] = new_config[section]

       return mvp_config
   ```

### Issue: API Integration Problems

**Symptoms:**
- Async/await compatibility issues
- Serialization errors
- Response format problems

**Solutions:**

1. **Async Integration Pattern**
   ```python
   import asyncio
   from orchestrator_dbt.run_multi_year import run_enhanced_multi_year_simulation

   class AsyncSimulationAPI:
       def __init__(self):
           self.loop = asyncio.new_event_loop()
           asyncio.set_event_loop(self.loop)

       def run_simulation_sync(self, **kwargs):
           """Synchronous wrapper for async simulation."""
           return self.loop.run_until_complete(
               run_enhanced_multi_year_simulation(**kwargs)
           )

       def __del__(self):
           if hasattr(self, 'loop'):
               self.loop.close()
   ```

2. **Serialization Handling**
   ```python
   import json
   from datetime import date, datetime

   def serialize_simulation_result(result):
       """Serialize simulation results for API responses."""
       def json_serializer(obj):
           if isinstance(obj, (date, datetime)):
               return obj.isoformat()
           elif hasattr(obj, '__dict__'):
               return obj.__dict__
           else:
               return str(obj)

       return json.dumps(result, default=json_serializer, indent=2)
   ```

## Error Messages and Solutions

### Common Error Messages

1. **"Sequential execution validation failed"**
   ```
   Error: Year 2026 is missing or incomplete. Cannot start simulation from year 2027.
   ```
   **Solution:**
   ```bash
   # Run years sequentially
   python -m orchestrator_dbt.run_multi_year --start-year 2025 --end-year 2026
   python -m orchestrator_dbt.run_multi_year --start-year 2027 --end-year 2029

   # Or use force-clear to start fresh
   python -m orchestrator_dbt.run_multi_year --start-year 2025 --end-year 2029 --force-clear
   ```

2. **"Foundation setup exceeded 10 second target"**
   ```
   Error: Foundation setup took 15.2s (target: <10s)
   ```
   **Solution:**
   ```bash
   # Optimize foundation setup
   python -m orchestrator_dbt.run_multi_year --foundation-only --batch-size 500 --optimization medium
   ```

3. **"Performance improvement target not met"**
   ```
   Error: Performance improvement 65% < 82% target
   ```
   **Solution:**
   ```bash
   # Use high-performance configuration
   python -m orchestrator_dbt.run_multi_year \
       --optimization high \
       --max-workers 8 \
       --batch-size 2000 \
       --enable-compression
   ```

4. **"Configuration validation failed"**
   ```
   Error: Invalid configuration: Missing required field: simulation.start_year
   ```
   **Solution:**
   ```yaml
   # Add missing required fields to configuration
   simulation:
     start_year: 2025      # Required
     end_year: 2029        # Required
     target_growth_rate: 0.03  # Required
   workforce:
     total_termination_rate: 0.12  # Required
   random_seed: 42  # Required
   ```

### Debug Mode

Enable debug mode for detailed troubleshooting:

```bash
# Enable maximum verbosity
python -m orchestrator_dbt.run_multi_year \
    --verbose \
    --structured-logs \
    --log-file debug.log \
    --foundation-only

# Enable Python debug mode
PYTHONPATH=. python -u -m orchestrator_dbt.run_multi_year --verbose
```

## Performance Tuning

### Optimization Strategies

1. **CPU-Bound Workloads**
   ```bash
   # Maximize CPU utilization
   python -m orchestrator_dbt.run_multi_year \
       --max-workers $(nproc) \
       --batch-size 2000 \
       --optimization high
   ```

2. **Memory-Constrained Environments**
   ```bash
   # Minimize memory usage
   python -m orchestrator_dbt.run_multi_year \
       --max-workers 2 \
       --batch-size 500 \
       --enable-compression \
       --optimization medium
   ```

3. **I/O-Bound Workloads**
   ```bash
   # Optimize for database operations
   python -m orchestrator_dbt.run_multi_year \
       --max-workers 4 \
       --batch-size 1500 \
       --optimization high
   ```

### Performance Monitoring

```python
import time
import psutil
from orchestrator_dbt.run_multi_year import PerformanceMonitor

class ComprehensiveMonitor:
    def __init__(self):
        self.performance_monitor = PerformanceMonitor()
        self.start_time = None

    def start_monitoring(self):
        self.performance_monitor.start()
        self.start_time = time.time()

    def log_system_metrics(self):
        """Log comprehensive system metrics."""
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        # Memory metrics
        memory = psutil.virtual_memory()
        memory_mb = memory.used / (1024**2)

        # Disk metrics
        disk = psutil.disk_usage('.')
        disk_used_gb = (disk.total - disk.free) / (1024**3)

        print(f"System Metrics:")
        print(f"  CPU: {cpu_percent}% ({cpu_count} cores)")
        print(f"  Memory: {memory_mb:.1f}MB ({memory.percent}%)")
        print(f"  Disk: {disk_used_gb:.1f}GB used")

        # Performance monitor metrics
        perf_summary = self.performance_monitor.get_summary()
        if perf_summary:
            print(f"  Peak Memory: {perf_summary['peak_memory_mb']:.1f}MB")
            print(f"  Memory Efficiency: {perf_summary['memory_efficiency']:.1%}")

# Usage
monitor = ComprehensiveMonitor()
monitor.start_monitoring()
# ... run simulation ...
monitor.log_system_metrics()
```

## Best Practices

### Development Best Practices

1. **Configuration Management**
   ```yaml
   # Use environment-specific configurations
   # config/development.yaml
   simulation:
     start_year: 2025
     end_year: 2026  # Shorter range for development
     target_growth_rate: 0.03

   # config/production.yaml
   simulation:
     start_year: 2025
     end_year: 2030  # Full range for production
     target_growth_rate: 0.03
   ```

2. **Testing Strategy**
   ```bash
   # Always test configuration first
   python -m orchestrator_dbt.run_multi_year --test-config --config config/test.yaml

   # Run foundation benchmark before full simulation
   python -m orchestrator_dbt.run_multi_year --foundation-only --benchmark

   # Use shorter year ranges for testing
   python -m orchestrator_dbt.run_multi_year --start-year 2025 --end-year 2026
   ```

3. **Error Handling**
   ```python
   import asyncio
   from orchestrator_dbt.run_multi_year import run_enhanced_multi_year_simulation, error_context

   async def robust_simulation():
       """Robust simulation with comprehensive error handling."""
       max_retries = 3

       for attempt in range(max_retries):
           try:
               with error_context("Multi-year simulation",
                                "Check system resources and configuration"):
                   result = await run_enhanced_multi_year_simulation(
                       start_year=2025,
                       end_year=2027,
                       optimization_level=OptimizationLevel.HIGH,
                       max_workers=4,
                       batch_size=1000,
                       enable_compression=True,
                       fail_fast=False
                   )
                   return result

           except Exception as e:
               print(f"Attempt {attempt + 1} failed: {e}")
               if attempt == max_retries - 1:
                   raise

               # Wait before retry with exponential backoff
               await asyncio.sleep(2 ** attempt)
   ```

### Production Best Practices

1. **Resource Planning**
   ```bash
   # Calculate resource requirements
   YEARS=$((END_YEAR - START_YEAR + 1))
   ESTIMATED_MEMORY=$((YEARS * 512))  # MB per year estimate
   RECOMMENDED_WORKERS=$(($(nproc) / 2))  # Conservative worker count

   echo "Estimated requirements:"
   echo "  Memory: ${ESTIMATED_MEMORY}MB"
   echo "  Workers: ${RECOMMENDED_WORKERS}"
   ```

2. **Monitoring Integration**
   ```python
   import logging
   import json
   from datetime import datetime

   def setup_production_logging():
       """Setup production-grade logging."""

       # Structured JSON logging for monitoring systems
       class JSONFormatter(logging.Formatter):
           def format(self, record):
               log_entry = {
                   'timestamp': datetime.utcnow().isoformat(),
                   'level': record.levelname,
                   'message': record.getMessage(),
                   'module': record.module,
                   'function': record.funcName,
                   'line': record.lineno
               }
               return json.dumps(log_entry)

       handler = logging.StreamHandler()
       handler.setFormatter(JSONFormatter())

       logger = logging.getLogger()
       logger.addHandler(handler)
       logger.setLevel(logging.INFO)
   ```

3. **Health Checks**
   ```python
   async def health_check():
       """Production health check endpoint."""
       health_status = {
           'status': 'healthy',
           'timestamp': datetime.utcnow().isoformat(),
           'checks': {}
       }

       # Check database connectivity
       try:
           import duckdb
           conn = duckdb.connect('simulation.duckdb')
           conn.execute("SELECT 1").fetchone()
           conn.close()
           health_status['checks']['database'] = 'ok'
       except Exception as e:
           health_status['checks']['database'] = f'error: {e}'
           health_status['status'] = 'unhealthy'

       # Check memory usage
       memory = psutil.virtual_memory()
       if memory.percent < 90:
           health_status['checks']['memory'] = 'ok'
       else:
           health_status['checks']['memory'] = f'high: {memory.percent}%'
           health_status['status'] = 'degraded'

       # Check disk space
       disk = psutil.disk_usage('.')
       disk_percent = (disk.used / disk.total) * 100
       if disk_percent < 85:
           health_status['checks']['disk'] = 'ok'
       else:
           health_status['checks']['disk'] = f'high: {disk_percent:.1f}%'
           health_status['status'] = 'degraded'

       return health_status
   ```

## Production Deployment

### Deployment Checklist

- [ ] System requirements verified
- [ ] Configuration validated
- [ ] Foundation setup benchmark < 10s
- [ ] Performance regression test passes (>82% improvement)
- [ ] Memory and CPU limits configured
- [ ] Monitoring and logging configured
- [ ] Health checks implemented
- [ ] Backup and recovery procedures tested
- [ ] Documentation updated

### Container Deployment

```dockerfile
# Dockerfile for orchestrator_dbt
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Set environment variables
ENV PYTHONPATH=/app
ENV DAGSTER_HOME=/app/.dagster

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import asyncio; from orchestrator_dbt.run_multi_year import test_configuration_compatibility; print('healthy')"

# Default command
CMD ["python", "-m", "orchestrator_dbt.run_multi_year", "--help"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator-dbt
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orchestrator-dbt
  template:
    metadata:
      labels:
        app: orchestrator-dbt
    spec:
      containers:
      - name: orchestrator-dbt
        image: orchestrator-dbt:latest
        resources:
          limits:
            memory: "4Gi"
            cpu: "4"
          requests:
            memory: "2Gi"
            cpu: "2"
        env:
        - name: PYTHONUNBUFFERED
          value: "1"
        volumeMounts:
        - name: config
          mountPath: /app/config
        - name: data
          mountPath: /app/data
      volumes:
      - name: config
        configMap:
          name: simulation-config
      - name: data
        persistentVolumeClaim:
          claimName: simulation-data
```

---

For additional troubleshooting support, consult the [API Reference](orchestrator_dbt_api_reference.md) and [Migration Guide](orchestrator_dbt_migration_guide.md).
