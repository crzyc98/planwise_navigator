# Quickstart: Self-Healing dbt Initialization

**Feature Branch**: `006-self-healing-dbt-init`
**Date**: 2025-12-12

## Overview

This feature automatically detects missing database tables and initializes them before simulation runs. Users no longer need to manually run `dbt seed` or `dbt build` for new workspaces.

## How It Works

1. **Before every simulation**, the system checks if required tables exist
2. **If tables are missing**, initialization runs automatically:
   - Seeds are loaded (`dbt seed --full-refresh`)
   - Foundation models are built (`dbt run --select tag:foundation`)
3. **Progress feedback** is displayed during initialization
4. **Simulation proceeds** once all tables are verified

## Usage

### Default Behavior (Auto-Initialize Enabled)

```python
from planalign_orchestrator.factory import create_orchestrator

# Create orchestrator - auto-initialization is enabled by default
orchestrator = create_orchestrator("config/simulation_config.yaml")

# Run simulation - will auto-initialize if needed
summary = orchestrator.execute_multi_year_simulation(
    start_year=2025,
    end_year=2027
)
```

### CLI Usage

```bash
# Normal simulation command - auto-initializes if needed
planalign simulate 2025-2027

# Expected output for new workspace:
# 🔍 Checking database tables...
# ⚠️  Missing 8 required tables
# 🌱 Loading seed data... (15s)
# 🏗️  Building foundation models... (35s)
# ✅ Initialization complete (52s)
# 📊 Starting simulation...
```

### Disable Auto-Initialization

```python
# Explicitly disable auto-initialization
orchestrator = create_orchestrator(
    "config/simulation_config.yaml",
    auto_initialize=False
)

# Manual initialization if needed
from planalign_orchestrator.self_healing import AutoInitializer

auto_init = AutoInitializer(
    db_manager=orchestrator.db_manager,
    dbt_runner=orchestrator.dbt_runner,
    verbose=True
)
result = auto_init.ensure_initialized()
```

## Required Tables

The system checks for these tables:

### Seed Tables (Tier 1)
- `config_age_bands`
- `config_tenure_bands`
- `config_job_levels`
- `comp_levers`
- `irs_contribution_limits`

### Foundation Models (Tier 2)
- `int_baseline_workforce`
- `int_employee_compensation_by_year`

**Note**: These 7 tables are the minimum required for simulation. Additional tables are created during the simulation workflow.

## Error Handling

### Concurrent Initialization

```python
from planalign_orchestrator.exceptions import ConcurrentInitializationError

try:
    result = auto_init.ensure_initialized()
except ConcurrentInitializationError as e:
    print(f"Another initialization in progress: {e.lock_file}")
    # Wait and retry, or fail
```

### Initialization Timeout

```python
from planalign_orchestrator.exceptions import InitializationTimeoutError

try:
    result = auto_init.ensure_initialized()
except InitializationTimeoutError as e:
    print(f"Timeout after {e.elapsed_seconds}s (limit: {e.timeout_seconds}s)")
    # Check system resources, retry with longer timeout
```

### Database Corruption

```python
from planalign_orchestrator.exceptions import DatabaseCorruptionError

try:
    result = auto_init.ensure_initialized()
except DatabaseCorruptionError as e:
    print(f"Database corrupted: {e.db_path}")
    # Offer to recreate database
```

## Testing

### Unit Tests

```python
import pytest
from tests.fixtures.database import empty_database

def test_auto_initialization_with_empty_db(empty_database):
    """Test that auto-initialization creates all required tables."""
    auto_init = AutoInitializer(
        db_manager=empty_database,
        dbt_runner=mock_dbt_runner,
        verbose=True
    )

    result = auto_init.ensure_initialized()

    assert result.success
    assert result.state == InitializationState.COMPLETED
    assert len(result.missing_tables_found) == 7  # 5 seeds + 2 foundation models
    assert len(result.tables_created) == 7
```

### Integration Test

```bash
# Create fresh workspace and run simulation
rm -rf /tmp/test_workspace
mkdir -p /tmp/test_workspace
cd /tmp/test_workspace

# Copy config but no database
cp /path/to/config/simulation_config.yaml .

# Run simulation - should auto-initialize
planalign simulate 2025 --verbose

# Verify tables exist
duckdb dbt/simulation.duckdb "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
```

## Configuration

No additional configuration required. Auto-initialization uses existing settings:

- **Database path**: Uses `get_database_path()` from config
- **dbt settings**: Uses existing dbt-duckdb configuration
- **Timeout**: 60 seconds (hardcoded per SC-003)

## Troubleshooting

### "Missing seed files" Error

```
InitializationError: Seed file not found: dbt/seeds/config_age_bands.csv
```

**Solution**: Ensure seed CSV files are present in `dbt/seeds/` directory.

### "Timeout" Error

```
InitializationTimeoutError: Initialization exceeded 60s timeout
```

**Solution**:
1. Check disk I/O performance
2. Verify dbt-duckdb is working (`dbt debug`)
3. Run manual initialization to diagnose: `dbt seed && dbt run --select tag:foundation`

### "Lock file exists" Error

```
ConcurrentInitializationError: Lock held by another process
```

**Solution**:
1. Check if another simulation is running
2. If not, remove stale lock: `rm dbt/.planalign_init.lock`
