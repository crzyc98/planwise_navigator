# Auto-Optimize Troubleshooting Guide - Fidelity PlanAlign Engine

**Epic E012 Compensation Tuning System - S047 Optimization Engine**
**Last Updated:** July 2025
**Target Audience:** Technical Users, System Administrators, Developers

---

## Overview

This guide provides comprehensive troubleshooting information for Fidelity PlanAlign Engine's Auto-Optimize system. It covers common issues, error patterns, diagnostic tools, and step-by-step resolution procedures.

### Quick Reference

| Issue Type | Symptom | Quick Fix | Section |
|-----------|---------|-----------|---------|
| Database Lock | "Conflicting lock is held" | Close IDE connections | [Database Issues](#database-issues) |
| Convergence Failure | Optimization doesn't converge | Try different algorithm | [Optimization Issues](#optimization-issues) |
| Memory Error | Process killed/out of memory | Reduce max_evaluations | [Performance Issues](#performance-issues) |
| Parameter Validation | "Parameter out of bounds" | Check parameter schema | [Parameter Issues](#parameter-issues) |
| Timeout | Optimization times out | Increase timeout or use synthetic mode | [Timeout Issues](#timeout-issues) |

---

## Diagnostic Tools

### 1. Health Check Script

Create a diagnostic script to check system health:

```python
#!/usr/bin/env python3
"""
Fidelity PlanAlign Engine Auto-Optimize Health Check Script
"""

import os
import sys
import time
import subprocess
import traceback
from pathlib import Path

def check_environment():
    """Check environment setup."""
    print("🔍 Checking Environment...")

    # Check Python version
    python_version = sys.version_info
    print(f"  Python: {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version < (3, 11):
        print("  ⚠️  Warning: Python 3.11+ recommended")

    # Check DAGSTER_HOME
    dagster_home = os.environ.get('DAGSTER_HOME')
    print(f"  DAGSTER_HOME: {dagster_home}")
    if not dagster_home:
        print("  ❌ DAGSTER_HOME not set")
        return False

    # Check database path
    db_path = "/Users/nicholasamaral/planalign_engine/simulation.duckdb"
    print(f"  Database: {db_path}")
    if not os.path.exists(db_path):
        print(f"  ⚠️  Database file not found: {db_path}")

    print("  ✅ Environment check complete")
    return True

def check_dependencies():
    """Check required Python packages."""
    print("\n🔍 Checking Dependencies...")

    required_packages = [
        ("scipy", "1.11.0"),
        ("numpy", "1.24.0"),
        ("pandas", "2.0.0"),
        ("plotly", "5.15.0"),
        ("streamlit", "1.39.0"),
        ("dagster", "1.8.12"),
        ("duckdb", "1.0.0")
    ]

    missing_packages = []

    for package, min_version in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} missing")
            missing_packages.append(package)

    if missing_packages:
        print(f"  📦 Install missing packages: pip install {' '.join(missing_packages)}")
        return False

    return True

def check_database_connection():
    """Test database connectivity."""
    print("\n🔍 Checking Database Connection...")

    try:
        import duckdb

        db_path = "/Users/nicholasamaral/planalign_engine/simulation.duckdb"
        conn = duckdb.connect(db_path)

        # Test basic query
        result = conn.execute("SELECT 1 as test").fetchone()
        if result and result[0] == 1:
            print("  ✅ Database connection successful")

        # Check key tables
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [table[0] for table in tables]

        required_tables = ["fct_workforce_snapshot", "int_effective_parameters"]
        for table in required_tables:
            if table in table_names:
                print(f"  ✅ Table exists: {table}")
            else:
                print(f"  ⚠️  Table missing: {table}")

        conn.close()
        return True

    except Exception as e:
        print(f"  ❌ Database connection failed: {e}")
        return False

def check_optimization_components():
    """Test optimization component imports."""
    print("\n🔍 Checking Optimization Components...")

    try:
        from orchestrator.optimization.constraint_solver import CompensationOptimizer
        print("  ✅ CompensationOptimizer import successful")

        from orchestrator.optimization.objective_functions import ObjectiveFunctions
        print("  ✅ ObjectiveFunctions import successful")

        from streamlit_dashboard.optimization_schemas import ParameterSchema
        print("  ✅ ParameterSchema import successful")

        # Test parameter schema
        schema = ParameterSchema()
        params = schema.get_all_parameter_names()
        print(f"  ✅ Parameter schema loaded: {len(params)} parameters")

        return True

    except Exception as e:
        print(f"  ❌ Component import failed: {e}")
        traceback.print_exc()
        return False

def test_synthetic_optimization():
    """Run a quick synthetic optimization test."""
    print("\n🔍 Testing Synthetic Optimization...")

    try:
        from orchestrator.optimization.constraint_solver import CompensationOptimizer
        from orchestrator.resources.duckdb_resource import DuckDBResource

        # Mock DuckDB resource for testing
        class MockDuckDBResource:
            def get_connection(self):
                import duckdb
                return duckdb.connect(":memory:")

        duckdb_resource = MockDuckDBResource()

        optimizer = CompensationOptimizer(
            duckdb_resource=duckdb_resource,
            scenario_id="health_check_test",
            use_synthetic=True
        )

        initial_parameters = {
            "merit_rate_level_1": 0.045,
            "cola_rate": 0.025
        }

        objectives = {"cost": 0.6, "equity": 0.4}

        print("    Running 5-evaluation test...")
        start_time = time.time()

        result = optimizer.optimize(
            initial_parameters=initial_parameters,
            objectives=objectives,
            method="SLSQP",
            max_evaluations=5,
            timeout_minutes=1,
            random_seed=42
        )

        runtime = time.time() - start_time
        print(f"    Test completed in {runtime:.2f}s")

        if hasattr(result, 'converged'):
            print(f"  ✅ Synthetic optimization test: {'converged' if result.converged else 'ran successfully'}")
            return True
        else:
            print(f"  ❌ Optimization failed: {result}")
            return False

    except Exception as e:
        print(f"  ❌ Synthetic optimization test failed: {e}")
        traceback.print_exc()
        return False

def run_health_check():
    """Run complete health check."""
    print("🏥 Fidelity PlanAlign Engine Auto-Optimize Health Check")
    print("=" * 50)

    checks = [
        check_environment,
        check_dependencies,
        check_database_connection,
        check_optimization_components,
        test_synthetic_optimization
    ]

    passed = 0
    total = len(checks)

    for check in checks:
        try:
            if check():
                passed += 1
        except Exception as e:
            print(f"  ❌ Check failed with exception: {e}")

    print(f"\n📊 Health Check Results: {passed}/{total} checks passed")

    if passed == total:
        print("🎉 System is healthy and ready for optimization!")
        return True
    else:
        print("⚠️  Some issues detected. See above for details.")
        return False

if __name__ == "__main__":
    success = run_health_check()
    sys.exit(0 if success else 1)
```

### 2. Log Analysis Tools

#### Extract Optimization Logs

```bash
#!/bin/bash
# extract_optimization_logs.sh

echo "📋 Extracting Optimization Logs..."

# Find recent Dagster logs
LOG_DIRS=(
    "$HOME/.dagster/storage/*/compute_logs"
    "$HOME/dagster_home_planwise/storage/*/compute_logs"
)

for pattern in "${LOG_DIRS[@]}"; do
    for log_dir in $pattern; do
        if [ -d "$log_dir" ]; then
            echo "Found logs in: $log_dir"

            # Extract optimization-related logs
            grep -r "optimization\|SLSQP\|objective\|converged" "$log_dir" \
                | tail -50 > optimization_logs.txt

            echo "Optimization logs saved to: optimization_logs.txt"
            break 2
        fi
    done
done
```

#### Performance Monitoring

```python
"""Performance monitoring utilities."""

import time
import psutil
import threading
from typing import Dict, List, Callable

class PerformanceMonitor:
    """Monitor system performance during optimization."""

    def __init__(self):
        self.monitoring = False
        self.metrics = []
        self.monitor_thread = None

    def start_monitoring(self, interval: float = 1.0):
        """Start performance monitoring."""
        self.monitoring = True
        self.metrics = []

        def monitor_loop():
            while self.monitoring:
                metrics = {
                    'timestamp': time.time(),
                    'cpu_percent': psutil.cpu_percent(interval=None),
                    'memory_mb': psutil.virtual_memory().used / 1024 / 1024,
                    'memory_percent': psutil.virtual_memory().percent
                }
                self.metrics.append(metrics)
                time.sleep(interval)

        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self) -> Dict:
        """Stop monitoring and return summary."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)

        if not self.metrics:
            return {}

        cpu_values = [m['cpu_percent'] for m in self.metrics]
        memory_values = [m['memory_mb'] for m in self.metrics]

        return {
            'duration_seconds': self.metrics[-1]['timestamp'] - self.metrics[0]['timestamp'],
            'avg_cpu_percent': sum(cpu_values) / len(cpu_values),
            'max_memory_mb': max(memory_values),
            'avg_memory_mb': sum(memory_values) / len(memory_values),
            'sample_count': len(self.metrics)
        }

# Usage example
monitor = PerformanceMonitor()
monitor.start_monitoring()

# Run optimization here...

performance_summary = monitor.stop_monitoring()
print(f"Performance Summary: {performance_summary}")
```

---

## Common Issues and Solutions

### Database Issues

#### Issue: "Conflicting lock is held on database"

**Symptoms:**
- Error message: "Conflicting lock is held"
- Optimization fails to start
- Database appears inaccessible

**Causes:**
- IDE (VS Code, Windsurf) database connections open
- Multiple optimization processes running
- Crashed processes holding locks

**Solutions:**

1. **Close IDE Database Connections:**
   ```bash
   # In VS Code/Windsurf, close any database explorer tabs
   # Close any SQL query windows
   # Restart IDE if necessary
   ```

2. **Check for Running Processes:**
   ```bash
   ps aux | grep -E "dagster|python.*optimization"
   # Kill any hanging optimization processes
   kill -9 <process_id>
   ```

3. **Force Database Unlock:**
   ```python
   import duckdb
   import os

   db_path = "/Users/nicholasamaral/planalign_engine/simulation.duckdb"

   # Close any existing connections
   try:
       conn = duckdb.connect(db_path)
       conn.close()
   except:
       pass

   # If still locked, check for .wal files
   wal_files = [f for f in os.listdir(os.path.dirname(db_path))
                if f.startswith(os.path.basename(db_path)) and f.endswith('.wal')]

   if wal_files:
       print(f"Found WAL files: {wal_files}")
       print("Consider restarting the system if database remains locked")
   ```

#### Issue: "Database file not found"

**Solutions:**
1. **Check Database Path:**
   ```python
   import os
   db_path = "/Users/nicholasamaral/planalign_engine/simulation.duckdb"
   if not os.path.exists(db_path):
       print(f"Database not found at: {db_path}")
       # Run initial simulation to create database
   ```

2. **Initialize Database:**
   ```bash
   cd /Users/nicholasamaral/planalign_engine
   dagster asset materialize --select simulation_year_state -f definitions.py
   ```

### Optimization Issues

#### Issue: Optimization Fails to Converge

**Symptoms:**
- `converged: False` in results
- High objective values
- Maximum iterations reached

**Diagnosis:**
```python
def diagnose_convergence_issue(optimizer, parameters, objectives):
    """Diagnose why optimization isn't converging."""

    print("🔍 Diagnosing Convergence Issues...")

    # Check parameter bounds
    from streamlit_dashboard.optimization_schemas import ParameterSchema
    schema = ParameterSchema()

    for param_name, value in parameters.items():
        param_def = schema.get_parameter(param_name)
        bounds = param_def.bounds

        if value <= bounds.min_value or value >= bounds.max_value:
            print(f"  ⚠️  {param_name} at boundary: {value} in [{bounds.min_value}, {bounds.max_value}]")

    # Test objective function
    try:
        obj_value = optimizer.obj_funcs.combined_objective(parameters, objectives)
        print(f"  📊 Initial objective value: {obj_value:.6f}")

        if obj_value > 100:
            print(f"  ⚠️  High objective value indicates poor starting point")

    except Exception as e:
        print(f"  ❌ Objective function error: {e}")

    # Test with synthetic mode
    if not optimizer.use_synthetic:
        print("  💡 Try with synthetic mode first")
```

**Solutions:**

1. **Try Different Algorithm:**
   ```python
   algorithms = ["SLSQP", "DE", "L-BFGS-B", "TNC"]

   for algorithm in algorithms:
       print(f"Trying algorithm: {algorithm}")
       result = optimizer.optimize(
           initial_parameters=parameters,
           objectives=objectives,
           method=algorithm,
           max_evaluations=50  # Start small
       )

       if hasattr(result, 'converged') and result.converged:
           print(f"✅ Converged with {algorithm}")
           break
   ```

2. **Adjust Starting Point:**
   ```python
   # Move away from parameter boundaries
   from streamlit_dashboard.optimization_schemas import ParameterSchema

   schema = ParameterSchema()
   adjusted_parameters = {}

   for param_name, value in parameters.items():
       param_def = schema.get_parameter(param_name)
       bounds = param_def.bounds

       # Move to center if at boundaries
       if value <= bounds.min_value + 0.001:
           adjusted_parameters[param_name] = bounds.default_value
       elif value >= bounds.max_value - 0.001:
           adjusted_parameters[param_name] = bounds.default_value
       else:
           adjusted_parameters[param_name] = value
   ```

3. **Relax Convergence Tolerance:**
   ```python
   # For SLSQP, adjust tolerance in optimizer options
   result = minimize(
       fun=objective_func,
       x0=initial_point,
       method='SLSQP',
       options={'ftol': 1e-4}  # Relaxed from 1e-6
   )
   ```

#### Issue: Oscillating Objective Values

**Symptoms:**
- Objective value bounces up and down
- No clear convergence trend
- "Iteration limit reached" messages

**Solutions:**

1. **Reduce Step Size (For Gradient-Based Methods):**
   ```python
   # Use more conservative optimization
   result = optimizer.optimize(
       parameters,
       objectives,
       method="L-BFGS-B",  # More stable than SLSQP
       max_evaluations=200
   )
   ```

2. **Switch to Evolutionary Algorithm:**
   ```python
   # Differential Evolution is more robust for noisy objectives
   result = optimizer.optimize(
       parameters,
       objectives,
       method="DE",
       max_evaluations=300  # DE needs more evaluations
   )
   ```

### Parameter Issues

#### Issue: "Parameter out of bounds" Errors

**Diagnosis Script:**
```python
def validate_all_parameters():
    """Check all parameters against schema."""
    from streamlit_dashboard.optimization_schemas import ParameterSchema

    schema = ParameterSchema()

    # Get current parameters from comp_levers.csv
    import pandas as pd
    comp_levers = pd.read_csv("dbt/seeds/comp_levers.csv")

    # Check each parameter
    for _, row in comp_levers.iterrows():
        param_name = row['parameter_name']
        value = row['parameter_value']

        if param_name in schema.get_all_parameter_names():
            param_def = schema.get_parameter(param_name)
            is_valid, messages, risk = param_def.validate_value(value)

            if not is_valid:
                print(f"❌ {param_name}: {value} - {messages}")
            elif risk == "HIGH":
                print(f"⚠️  {param_name}: {value} - High risk")
```

**Solutions:**

1. **Auto-Fix Parameter Bounds:**
   ```python
   def fix_parameter_bounds(parameters):
       """Automatically fix parameter bounds violations."""
       from streamlit_dashboard.optimization_schemas import ParameterSchema

       schema = ParameterSchema()
       fixed_parameters = {}

       for param_name, value in parameters.items():
           param_def = schema.get_parameter(param_name)
           bounds = param_def.bounds

           # Clamp to bounds
           fixed_value = max(bounds.min_value, min(bounds.max_value, value))

           if fixed_value != value:
               print(f"🔧 Fixed {param_name}: {value:.4f} → {fixed_value:.4f}")

           fixed_parameters[param_name] = fixed_value

       return fixed_parameters
   ```

### Performance Issues

#### Issue: Out of Memory Errors

**Symptoms:**
- Process killed by OS
- "MemoryError" exceptions
- System becomes unresponsive

**Solutions:**

1. **Reduce Memory Usage:**
   ```python
   # Reduce cache size
   optimizer.cache.cache_size = 1000  # Default: 10000

   # Use synthetic mode
   optimizer.use_synthetic = True

   # Reduce max evaluations
   result = optimizer.optimize(
       parameters,
       objectives,
       max_evaluations=50,  # Reduced from 200
       timeout_minutes=30
   )
   ```

2. **Monitor Memory Usage:**
   ```python
   import psutil
   import gc

   def optimize_with_memory_monitoring():
       process = psutil.Process()

       for i in range(max_evaluations):
           # Run evaluation
           objective_value = evaluate_objective(parameters)

           # Check memory usage
           memory_mb = process.memory_info().rss / 1024 / 1024
           if memory_mb > 4000:  # 4GB limit
               print(f"⚠️  High memory usage: {memory_mb:.1f} MB")
               gc.collect()  # Force garbage collection

           if memory_mb > 6000:  # 6GB abort
               print("❌ Memory limit exceeded - stopping optimization")
               break
   ```

#### Issue: Very Slow Performance

**Diagnosis:**
```python
def benchmark_performance():
    """Benchmark optimization components."""
    import time

    print("🔍 Performance Benchmark...")

    # Test parameter validation
    start = time.time()
    schema = ParameterSchema()
    for _ in range(1000):
        schema.validate_parameter_set(test_parameters)
    validation_time = time.time() - start
    print(f"  Parameter validation: {validation_time:.3f}s per 1000 calls")

    # Test objective function
    start = time.time()
    for _ in range(10):
        obj_value = obj_funcs.combined_objective(parameters, objectives)
    objective_time = (time.time() - start) / 10
    print(f"  Objective function: {objective_time:.3f}s per call")

    if objective_time > 5.0:
        print("  ⚠️  Slow objective function - consider synthetic mode")
```

**Solutions:**

1. **Use Synthetic Mode for Development:**
   ```python
   # 100x speed improvement for testing
   optimizer = CompensationOptimizer(
       duckdb_resource=duckdb_resource,
       scenario_id="fast_test",
       use_synthetic=True
   )
   ```

2. **Optimize Database Queries:**
   ```sql
   -- Add indexes for frequently queried columns
   CREATE INDEX IF NOT EXISTS idx_workforce_simulation_year
   ON fct_workforce_snapshot(simulation_year);

   CREATE INDEX IF NOT EXISTS idx_parameters_year
   ON int_effective_parameters(year);
   ```

3. **Parallel Processing:**
   ```python
   # For evolutionary algorithms
   result = optimizer.optimize(
       parameters,
       objectives,
       method="DE",
       max_evaluations=200,
       workers=4  # Use multiple CPU cores
   )
   ```

### Timeout Issues

#### Issue: Optimization Times Out

**Symptoms:**
- "Optimization timeout reached" messages
- Incomplete results
- Process terminates early

**Solutions:**

1. **Adjust Timeout Dynamically:**
   ```python
   def calculate_optimal_timeout(max_evaluations, use_synthetic):
       """Calculate reasonable timeout based on settings."""
       if use_synthetic:
           # Synthetic mode: ~0.01s per evaluation
           return max(5, max_evaluations * 0.02 / 60)  # minutes
       else:
           # Real mode: ~30-60s per evaluation
           return max(15, max_evaluations * 1.0)  # minutes

   timeout = calculate_optimal_timeout(100, use_synthetic=False)
   print(f"Setting timeout to {timeout:.1f} minutes")
   ```

2. **Progressive Timeout Strategy:**
   ```python
   def optimize_with_progressive_timeout():
       """Try optimization with increasing timeouts."""
       timeouts = [15, 30, 60, 120]  # minutes
       evaluations = [25, 50, 100, 200]

       for timeout, max_eval in zip(timeouts, evaluations):
           print(f"Trying {max_eval} evaluations with {timeout}min timeout...")

           result = optimizer.optimize(
               parameters,
               objectives,
               max_evaluations=max_eval,
               timeout_minutes=timeout
           )

           if hasattr(result, 'converged') and result.converged:
               print(f"✅ Converged with {max_eval} evaluations")
               return result

           print(f"⏭️  Trying longer timeout...")

       print("❌ Failed to converge with all timeout settings")
       return result
   ```

### Dagster Integration Issues

#### Issue: Asset Materialization Fails

**Symptoms:**
- "Asset materialization failed" in Dagster UI
- Python import errors
- Configuration not found

**Solutions:**

1. **Check Dagster Configuration:**
   ```bash
   # Verify DAGSTER_HOME
   echo $DAGSTER_HOME

   # Check if it's set system-wide
   launchctl getenv DAGSTER_HOME

   # Set if missing
   ./scripts/set_dagster_home.sh
   ```

2. **Validate Asset Definition:**
   ```python
   # Test asset import
   try:
       from definitions import defs
       asset_def = defs.get_asset_def("advanced_optimization_engine")
       print("✅ Asset definition loaded successfully")
   except Exception as e:
       print(f"❌ Asset definition error: {e}")
   ```

3. **Check Configuration File:**
   ```python
   import os
   import yaml

   config_path = "/tmp/planwise_optimization_config.yaml"

   if os.path.exists(config_path):
       with open(config_path, 'r') as f:
           config = yaml.safe_load(f)
       print("✅ Configuration file exists")
       print(f"Config keys: {list(config.keys())}")
   else:
       print("❌ Configuration file missing")
       # Create minimal config
       minimal_config = {
           "optimization": {
               "scenario_id": "test_scenario",
               "initial_parameters": {"merit_rate_level_1": 0.045},
               "objectives": {"cost": 1.0},
               "use_synthetic": True
           }
       }
       with open(config_path, 'w') as f:
           yaml.dump(minimal_config, f)
       print("🔧 Created minimal configuration file")
   ```

---

## Step-by-Step Resolution Procedures

### Procedure 1: Complete System Reset

When multiple issues occur simultaneously:

```bash
#!/bin/bash
# complete_system_reset.sh

echo "🔄 Complete System Reset for Auto-Optimize"

# 1. Stop all related processes
echo "1. Stopping processes..."
pkill -f "dagster"
pkill -f "streamlit"
pkill -f "optimization"

# 2. Close database connections
echo "2. Closing database connections..."
# Manual step: Close VS Code/IDE database connections

# 3. Clean temporary files
echo "3. Cleaning temporary files..."
rm -f /tmp/planwise_optimization_*.yaml
rm -f /tmp/optimization_result.pkl
rm -f /tmp/*optimization*.pkl

# 4. Reset Dagster home
echo "4. Resetting Dagster home..."
export DAGSTER_HOME=~/dagster_home_planwise
./scripts/set_dagster_home.sh

# 5. Restart virtual environment
echo "5. Reactivating virtual environment..."
source venv/bin/activate

# 6. Test basic functionality
echo "6. Testing basic functionality..."
python3 -c "
import sys
print(f'Python: {sys.version}')

try:
    from orchestrator.optimization.constraint_solver import CompensationOptimizer
    print('✅ Optimization imports working')
except Exception as e:
    print(f'❌ Import error: {e}')

try:
    import duckdb
    conn = duckdb.connect('simulation.duckdb')
    result = conn.execute('SELECT 1').fetchone()
    conn.close()
    print('✅ Database connection working')
except Exception as e:
    print(f'❌ Database error: {e}')
"

echo "🎉 System reset complete"
```

### Procedure 2: Gradual Problem Isolation

For systematic troubleshooting:

```python
def isolate_optimization_problem():
    """Systematically isolate optimization issues."""

    print("🔍 Starting Problem Isolation...")

    # Test 1: Parameter Schema
    print("\n1. Testing Parameter Schema...")
    try:
        from streamlit_dashboard.optimization_schemas import ParameterSchema
        schema = ParameterSchema()
        param_names = schema.get_all_parameter_names()
        print(f"  ✅ Schema loaded: {len(param_names)} parameters")
    except Exception as e:
        print(f"  ❌ Schema error: {e}")
        return "SCHEMA_ERROR"

    # Test 2: Database Connection
    print("\n2. Testing Database Connection...")
    try:
        import duckdb
        conn = duckdb.connect("simulation.duckdb")
        tables = conn.execute("SHOW TABLES").fetchall()
        conn.close()
        print(f"  ✅ Database: {len(tables)} tables found")
    except Exception as e:
        print(f"  ❌ Database error: {e}")
        return "DATABASE_ERROR"

    # Test 3: Synthetic Optimization
    print("\n3. Testing Synthetic Optimization...")
    try:
        from orchestrator.optimization.constraint_solver import CompensationOptimizer

        class MockResource:
            def get_connection(self):
                import duckdb
                return duckdb.connect(":memory:")

        optimizer = CompensationOptimizer(
            duckdb_resource=MockResource(),
            scenario_id="isolation_test",
            use_synthetic=True
        )

        result = optimizer.optimize(
            initial_parameters={"merit_rate_level_1": 0.045},
            objectives={"cost": 1.0},
            max_evaluations=3,
            timeout_minutes=1
        )

        print("  ✅ Synthetic optimization working")
    except Exception as e:
        print(f"  ❌ Synthetic optimization error: {e}")
        return "OPTIMIZATION_ERROR"

    # Test 4: Real Database Optimization
    print("\n4. Testing Real Database Optimization...")
    try:
        from orchestrator.resources.duckdb_resource import DuckDBResource

        duckdb_resource = DuckDBResource(
            database_path="simulation.duckdb"
        )

        optimizer = CompensationOptimizer(
            duckdb_resource=duckdb_resource,
            scenario_id="real_isolation_test",
            use_synthetic=False
        )

        # Very small test
        result = optimizer.optimize(
            initial_parameters={"merit_rate_level_1": 0.045},
            objectives={"cost": 1.0},
            max_evaluations=2,
            timeout_minutes=2
        )

        print("  ✅ Real optimization working")
        return "ALL_WORKING"

    except Exception as e:
        print(f"  ❌ Real optimization error: {e}")
        return "REAL_OPTIMIZATION_ERROR"

# Run isolation
issue = isolate_optimization_problem()
print(f"\n🎯 Issue isolated: {issue}")
```

### Procedure 3: Performance Optimization

For slow performance issues:

```python
def optimize_performance():
    """Apply performance optimizations."""

    print("⚡ Applying Performance Optimizations...")

    # 1. Database optimizations
    print("1. Optimizing database...")
    import duckdb

    conn = duckdb.connect("simulation.duckdb")

    # Add indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_workforce_year ON fct_workforce_snapshot(simulation_year)",
        "CREATE INDEX IF NOT EXISTS idx_parameters_year ON int_effective_parameters(year)",
        "CREATE INDEX IF NOT EXISTS idx_events_year ON fct_yearly_events(simulation_year)"
    ]

    for index_sql in indexes:
        try:
            conn.execute(index_sql)
            print(f"  ✅ Index created")
        except Exception as e:
            print(f"  ⚠️  Index creation failed: {e}")

    # Analyze tables
    conn.execute("ANALYZE")
    print("  ✅ Tables analyzed")
    conn.close()

    # 2. Memory optimizations
    print("2. Configuring memory settings...")
    import gc

    # Force garbage collection
    gc.collect()

    # Set garbage collection thresholds
    gc.set_threshold(700, 10, 10)
    print("  ✅ Memory settings optimized")

    # 3. Cache optimizations
    print("3. Optimizing cache settings...")
    # These would be applied in optimizer initialization
    cache_settings = {
        "cache_size": 5000,      # Reduced from 10000
        "cache_tolerance": 1e-5, # Slightly relaxed
        "enable_compression": True
    }
    print(f"  ✅ Recommended cache settings: {cache_settings}")

    print("⚡ Performance optimization complete")
```

---

## Monitoring and Alerts

### Real-time Monitoring Setup

```python
"""Set up real-time monitoring for optimization processes."""

import time
import logging
import threading
from typing import Dict, List

class OptimizationMonitor:
    """Monitor optimization health and performance."""

    def __init__(self):
        self.alerts = []
        self.monitoring = False
        self.logger = logging.getLogger(__name__)

    def start_monitoring(self):
        """Start background monitoring."""
        self.monitoring = True
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.monitoring:
            try:
                # Check system resources
                self._check_memory_usage()
                self._check_database_locks()
                self._check_process_health()

                time.sleep(10)  # Check every 10 seconds

            except Exception as e:
                self.logger.error(f"Monitoring error: {e}")

    def _check_memory_usage(self):
        """Check memory usage and alert if high."""
        import psutil

        memory = psutil.virtual_memory()
        if memory.percent > 85:
            alert = f"High memory usage: {memory.percent:.1f}%"
            self._add_alert("MEMORY", alert)

    def _check_database_locks(self):
        """Check for database lock issues."""
        try:
            import duckdb
            conn = duckdb.connect("simulation.duckdb", read_only=True)
            conn.execute("SELECT 1")
            conn.close()
        except Exception as e:
            if "lock" in str(e).lower():
                self._add_alert("DATABASE", f"Database lock detected: {e}")

    def _check_process_health(self):
        """Check optimization process health."""
        import subprocess

        try:
            # Check for hanging optimization processes
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )

            optimization_processes = [
                line for line in result.stdout.split('\n')
                if 'optimization' in line and 'python' in line
            ]

            if len(optimization_processes) > 3:
                self._add_alert("PROCESS", f"Multiple optimization processes detected: {len(optimization_processes)}")

        except Exception as e:
            self.logger.error(f"Process health check failed: {e}")

    def _add_alert(self, category: str, message: str):
        """Add alert if not already present."""
        alert = {"category": category, "message": message, "timestamp": time.time()}

        # Don't duplicate recent alerts
        recent_alerts = [a for a in self.alerts if time.time() - a["timestamp"] < 300]
        duplicate = any(a["message"] == message for a in recent_alerts)

        if not duplicate:
            self.alerts.append(alert)
            self.logger.warning(f"ALERT [{category}]: {message}")

    def get_alerts(self, max_age_minutes: int = 60) -> List[Dict]:
        """Get recent alerts."""
        cutoff = time.time() - (max_age_minutes * 60)
        return [a for a in self.alerts if a["timestamp"] > cutoff]

    def stop_monitoring(self):
        """Stop monitoring."""
        self.monitoring = False

# Usage
monitor = OptimizationMonitor()
monitor.start_monitoring()

# Check alerts periodically
alerts = monitor.get_alerts()
if alerts:
    print(f"⚠️  {len(alerts)} active alerts:")
    for alert in alerts:
        print(f"  - [{alert['category']}] {alert['message']}")
```

### Automated Health Checks

```bash
#!/bin/bash
# automated_health_check.sh

# Run health checks every 5 minutes
while true; do
    echo "$(date): Running health check..."

    # Check database accessibility
    python3 -c "
import duckdb
try:
    conn = duckdb.connect('simulation.duckdb', read_only=True)
    conn.execute('SELECT 1')
    conn.close()
    print('✅ Database accessible')
except Exception as e:
    print(f'❌ Database error: {e}')
    exit(1)
"

    # Check memory usage
    memory_usage=$(free | grep Mem | awk '{print ($3/$2) * 100.0}')
    if (( $(echo "$memory_usage > 90" | bc -l) )); then
        echo "⚠️  High memory usage: ${memory_usage}%"
    fi

    # Check disk space
    disk_usage=$(df /Users/nicholasamaral/planalign_engine | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 85 ]; then
        echo "⚠️  High disk usage: ${disk_usage}%"
    fi

    sleep 300  # Wait 5 minutes
done
```

---

## Recovery Procedures

### Emergency Stop Procedure

```python
def emergency_stop_optimization():
    """Emergency procedure to stop all optimization processes."""

    print("🚨 EMERGENCY STOP - Terminating all optimization processes")

    import subprocess
    import time
    import os
    import signal

    # 1. Find and kill optimization processes
    try:
        result = subprocess.run(
            ["pgrep", "-f", "optimization|dagster.*materialize"],
            capture_output=True,
            text=True
        )

        if result.stdout:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    print(f"  Terminated process {pid}")
                except:
                    pass

            # Wait and force kill if necessary
            time.sleep(5)

            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    print(f"  Force killed process {pid}")
                except:
                    pass

    except Exception as e:
        print(f"Error stopping processes: {e}")

    # 2. Clean up temporary files
    temp_files = [
        "/tmp/planwise_optimization_config.yaml",
        "/tmp/optimization_result.pkl",
        "/tmp/planwise_optimization_result.pkl"
    ]

    for temp_file in temp_files:
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                print(f"  Removed {temp_file}")
        except Exception as e:
            print(f"Error removing {temp_file}: {e}")

    # 3. Reset optimization cache
    try:
        # Clear any cached results in session state
        import streamlit as st
        if hasattr(st, 'session_state'):
            cache_keys = [k for k in st.session_state.keys() if 'optimization' in k.lower()]
            for key in cache_keys:
                del st.session_state[key]
                print(f"  Cleared cache key: {key}")
    except:
        pass

    print("🚨 Emergency stop complete")
```

### Data Recovery Procedure

```python
def recover_optimization_data():
    """Attempt to recover optimization data after system failure."""

    print("🔄 Attempting data recovery...")

    import os
    import glob
    import pickle
    import json

    # 1. Look for backup result files
    search_patterns = [
        "/tmp/*optimization*.pkl",
        "~/.dagster/storage/*/advanced_optimization_engine*",
        "/var/tmp/*optimization*"
    ]

    found_files = []
    for pattern in search_patterns:
        try:
            files = glob.glob(os.path.expanduser(pattern))
            found_files.extend(files)
        except:
            pass

    if found_files:
        print(f"Found {len(found_files)} potential recovery files:")
        for file_path in found_files:
            try:
                file_size = os.path.getsize(file_path)
                file_time = os.path.getmtime(file_path)
                print(f"  {file_path} ({file_size} bytes, {time.ctime(file_time)})")
            except:
                pass

    # 2. Try to load the most recent file
    if found_files:
        latest_file = max(found_files, key=lambda f: os.path.getmtime(f))

        try:
            with open(latest_file, 'rb') as f:
                data = pickle.load(f)

            print(f"✅ Successfully recovered data from {latest_file}")
            return data

        except Exception as e:
            print(f"❌ Failed to load {latest_file}: {e}")

    # 3. Check database for partial results
    try:
        import duckdb
        conn = duckdb.connect("simulation.duckdb")

        # Look for recent optimization metadata
        result = conn.execute("""
            SELECT * FROM fct_workforce_snapshot
            WHERE simulation_year >= 2025
            ORDER BY simulation_year DESC
            LIMIT 5
        """).fetchall()

        if result:
            print(f"✅ Found {len(result)} recent simulation records in database")
            return {"database_records": result}

        conn.close()

    except Exception as e:
        print(f"❌ Database recovery failed: {e}")

    print("❌ No recoverable data found")
    return None
```

---

## Support Escalation

### When to Escalate

Escalate to technical support when:

1. **System-level issues** that persist after following this guide
2. **Data corruption** or database integrity problems
3. **Performance degradation** that affects production workflows
4. **Security concerns** or unexpected behavior
5. **Bug reports** with clear reproduction steps

### Information to Gather

Before escalating, collect:

```python
def gather_support_information():
    """Gather comprehensive information for support escalation."""

    import sys
    import os
    import platform
    import subprocess
    from datetime import datetime

    info = {
        "timestamp": datetime.now().isoformat(),
        "system": {
            "platform": platform.platform(),
            "python_version": sys.version,
            "working_directory": os.getcwd(),
            "environment_variables": {
                "DAGSTER_HOME": os.environ.get("DAGSTER_HOME"),
                "PATH": os.environ.get("PATH")[:200] + "..."  # Truncated
            }
        },
        "database": {},
        "optimization": {},
        "recent_logs": []
    }

    # Database information
    try:
        import duckdb
        conn = duckdb.connect("simulation.duckdb")

        tables = conn.execute("SHOW TABLES").fetchall()
        info["database"]["tables"] = [t[0] for t in tables]

        # Check key table sizes
        for table_name in ["fct_workforce_snapshot", "int_effective_parameters"]:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                info["database"][f"{table_name}_count"] = count
            except:
                info["database"][f"{table_name}_count"] = "ERROR"

        conn.close()

    except Exception as e:
        info["database"]["error"] = str(e)

    # Optimization component versions
    try:
        import scipy
        import numpy
        import pandas
        import streamlit
        import dagster

        info["optimization"]["versions"] = {
            "scipy": scipy.__version__,
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "streamlit": streamlit.__version__,
            "dagster": dagster.__version__
        }

    except Exception as e:
        info["optimization"]["version_error"] = str(e)

    # Recent error logs
    try:
        log_patterns = [
            "optimization_logs.txt",
            "/tmp/dagster*.log"
        ]

        for pattern in log_patterns:
            if os.path.exists(pattern):
                with open(pattern, 'r') as f:
                    lines = f.readlines()
                    info["recent_logs"].extend(lines[-20:])  # Last 20 lines

    except Exception as e:
        info["recent_logs"] = [f"Log collection error: {e}"]

    return info

# Generate support package
support_info = gather_support_information()

# Save to file
import json
with open("support_package.json", "w") as f:
    json.dump(support_info, f, indent=2)

print("📦 Support package created: support_package.json")
```

### Contact Information

- **GitHub Issues**: [Repository Issues Page]
- **Technical Support**: [Support Email]
- **Community Forum**: [Forum Link]
- **Documentation**: [Main Documentation]

---

*This troubleshooting guide is part of the Fidelity PlanAlign Engine E012 Compensation Tuning System documentation suite.*
