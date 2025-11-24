# Fidelity PlanAlign Engine - Production Hardening Plan v2

## Core Philosophy (unchanged)
- Fix what's broken, don't add fancy features
- Use Claude Code for heavy lifting, ChatGPT for quick fixes
- No new packages, no architecture changes
- Each day produces something that immediately improves production

---

## Day 0 (Sunday Evening): Quick Prep
**Goal:** Ensure you can actually work on this without surprises
**Time:** 30 minutes

```bash
# 1. Capture baseline (know what "working" looks like)
python -m planalign_orchestrator.cli run --years 2025-2025
cp dbt/simulation.duckdb dbt/baseline.duckdb
cp runs.log baseline_runs.log

# 2. Freeze current environment
pip freeze > requirements_baseline.txt

# 3. Quick check with stakeholder (5 min call/slack)
# "We're fixing: backups, logging, hiring bugs, recovery. Anything else critical?"
```

---

## Day 1 (Monday): Safety First
**Goal:** Never lose data, never expose secrets

### Morning (2 hours)
```python
# Task 1: Smarter backups with rotation
import shutil
from datetime import datetime
import os

def create_backup():
    """Create timestamped backup and maintain 'latest' symlink"""
    if not os.path.exists('dbt/simulation.duckdb'):
        return

    # Create backups directory
    os.makedirs('dbt/backups', exist_ok=True)

    # Timestamped backup
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'dbt/backups/backup_{timestamp}.duckdb'

    # Copy to temp file first (safer)
    temp_path = f'{backup_path}.tmp'
    shutil.copy2('dbt/simulation.duckdb', temp_path)
    os.rename(temp_path, backup_path)  # Atomic on same filesystem

    # Update 'latest' link
    latest_path = 'dbt/backups/backup_latest.duckdb'
    if os.path.exists(latest_path):
        os.remove(latest_path)
    shutil.copy2(backup_path, latest_path)

    # Clean old backups (keep last 5)
    cleanup_old_backups('dbt/backups', keep=5)

    return backup_path
```

### Afternoon (2 hours)
```bash
# Task 2: Secure credentials
# Create .env.example (for documentation)
cat > .env.example << EOF
GEMINI_API_KEY=your_key_here
DB_PATH=dbt/simulation.duckdb
LOG_LEVEL=INFO
EOF

# Create actual .env (don't commit this!)
cp .env.example .env
# Edit .env with real values

# Add to .gitignore
echo ".env" >> .gitignore
echo "dbt/backups/" >> .gitignore
```

```python
# In config.py (centralized config loading)
import os
from dotenv import load_dotenv

load_dotenv()

# Validate required vars at startup
REQUIRED_VARS = ['GEMINI_API_KEY', 'DB_PATH']
for var in REQUIRED_VARS:
    if not os.getenv(var):
        raise ValueError(f"Missing required environment variable: {var}")

# Simple secret masking in logs
def mask_secrets(text):
    """Hide anything that looks like a key/token"""
    import re
    return re.sub(r'(api_key|token|password)=[^\s]+', r'\1=***', text, flags=re.IGNORECASE)
```

**Verify:**
- Run backup function, check `dbt/backups/` has timestamped file + latest
- Confirm no API keys in code with: `grep -r "api_key" --include="*.py"`

---

## Day 2 (Tuesday): Know What's Happening
**Goal:** Useful logs with context

### Morning (3 hours)
```python
# Add run_id and structured logging
import uuid
import json
from datetime import datetime

# Generate run_id at start of each run
RUN_ID = f"{datetime.now():%Y%m%d_%H%M%S}-{str(uuid.uuid4())[:8]}"

# Simple JSON logger
def log_event(level, message, **kwargs):
    """Log as JSON for easy parsing"""
    entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'run_id': RUN_ID,
        'level': level,
        'message': message,
        **kwargs
    }

    # Write to both console and file
    print(f"[{level}] {message}")  # Human readable

    with open(f'logs/run_{RUN_ID}.jsonl', 'a') as f:
        f.write(json.dumps(entry) + '\n')  # Machine readable

# Use it everywhere
log_event('INFO', 'Starting simulation', year=2025, config='simulation_config.yaml')
log_event('ERROR', 'dbt model failed', model='int_hiring_events', error=str(e))
log_event('INFO', 'Year complete', year=2025, duration_sec=45.2, rows_processed=1500)
```

### Afternoon (1 hour)
```python
# Add summary at end of run
def write_run_summary():
    """Create a summary for quick review"""
    summary = {
        'run_id': RUN_ID,
        'status': 'success' if not errors else 'failed',
        'start_time': start_time,
        'end_time': datetime.now().isoformat(),
        'years_processed': years_completed,
        'total_rows': total_rows,
        'errors': errors,
        'backup_created': backup_path
    }

    # Save summary
    with open(f'artifacts/runs/{RUN_ID}/summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    # Print to console
    print(f"\n=== Run {RUN_ID} Complete ===")
    print(f"Status: {summary['status']}")
    print(f"Duration: {summary['end_time'] - summary['start_time']}")
    if errors:
        print(f"Errors: {len(errors)}")
```

**Verify:** Run simulation, check `logs/run_*.jsonl` exists and has useful info

---

## Day 3 (Wednesday): Catch Data Problems Early
**Goal:** Fix the hiring/compensation bugs once and for all

### Use Claude Code for all of Day 3
```yaml
# In models/marts/schema.yml - enhance tests to show failing rows
models:
  - name: int_hiring_events
    tests:
      - name: no_null_compensation
        sql: |
          -- Returns actual failing rows for debugging
          select
            employee_id,
            year,
            hire_date,
            'NULL compensation on hire' as issue
          from int_hiring_events
          where total_compensation is null

  - name: int_workforce_needs_by_level
    tests:
      - name: hiring_happened_when_needed
        sql: |
          select
            w.year,
            w.level,
            w.hires_needed,
            count(h.employee_id) as hires_made,
            'Needed hires not created' as issue
          from int_workforce_needs_by_level w
          left join int_hiring_events h
            on w.year = h.year and w.level = h.level
          where w.hires_needed > 0
          group by w.year, w.level, w.hires_needed
          having count(h.employee_id) = 0

  - name: fct_workforce_snapshot
    tests:
      # Basic sanity checks
      - unique:
          column_name: "(employee_id || '-' || simulation_year)"
      - not_null:
          column_name: employee_id
      - not_null:
          column_name: base_salary
      # Value checks
      - dbt_utils.expression_is_true:
          expression: "base_salary >= 0"
      - dbt_utils.expression_is_true:
          expression: "years_of_service >= 0"
```

```python
# Add data quality summary after each year
def check_data_quality(year):
    """Run key checks and log results"""
    checks = {
        'workforce_count': "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
        'avg_compensation': "SELECT AVG(total_compensation) FROM fct_workforce_snapshot WHERE simulation_year = ?",
        'null_comp_count': "SELECT COUNT(*) FROM int_hiring_events WHERE year = ? AND total_compensation IS NULL",
        'contribution_coverage': "SELECT COUNT(DISTINCT employee_id) FROM int_employee_contributions WHERE year = ?"
    }

    results = {}
    for check_name, query in checks.items():
        result = db.execute(query, [year]).fetchone()[0]
        results[check_name] = result

        # Log warnings for suspicious values
        if check_name == 'null_comp_count' and result > 0:
            log_event('WARNING', f'Found {result} hires with NULL compensation', year=year)

    return results
```

**Verify:**
- Run `dbt test --select int_hiring_events` - should show actual failing rows
- Check that warnings appear in logs for data issues

---

## Day 4 (Thursday): Fast Recovery
**Goal:** When it breaks, fix it without starting over

### Morning (2 hours)
```python
# Better checkpoint system
def save_checkpoint(year, status='complete'):
    """Save checkpoint with validation hash"""
    checkpoint_data = {
        'year': year,
        'status': status,
        'run_id': RUN_ID,
        'timestamp': datetime.now().isoformat(),
        'input_hash': hash_config(),  # Hash of config that affects this year
        'row_counts': {
            'workforce': count_rows('fct_workforce_snapshot', year),
            'events': count_rows('fct_yearly_events', year)
        }
    }

    # Write as .partial during processing
    partial_path = f'.checkpoints/year_{year}.partial'
    done_path = f'.checkpoints/year_{year}.done'

    with open(partial_path, 'w') as f:
        json.dump(checkpoint_data, f)

    if status == 'complete':
        # Atomic rename when done
        os.rename(partial_path, done_path)

    return checkpoint_data

def can_skip_year(year):
    """Check if year can be safely skipped"""
    done_path = f'.checkpoints/year_{year}.done'
    if not os.path.exists(done_path):
        return False

    with open(done_path) as f:
        checkpoint = json.load(f)

    # Verify config hasn't changed
    if checkpoint.get('input_hash') != hash_config():
        log_event('INFO', f'Config changed, reprocessing year {year}')
        return False

    return True
```

### Afternoon (2 hours)
```markdown
# RECOVERY.md - Enhanced Recovery Guide

## Quick Diagnosis Table

| Error in logs | What it means | Fix command |
|---|---|---|
| `dbt model int_hiring_events failed` | Hiring logic broke | `dbt run --select int_workforce_needs_by_level int_hiring_events` |
| `NOT NULL constraint failed: total_compensation` | Missing comp data | `dbt run --select int_employee_compensation_by_year+` |
| `Run failed at year 2026` | Mid-run failure | `python -m planalign_orchestrator.cli run --resume` |
| `DuckDB Error: database is locked` | Concurrent access | Kill other processes: `fuser -k dbt/simulation.duckdb` |
| `No space left on device` | Disk full | Clean old backups: `rm dbt/backups/backup_2024*` |

## Full Reset Procedure
1. Stop any running processes
2. Restore from backup:
   ```bash
   cp dbt/backups/backup_latest.duckdb dbt/simulation.duckdb
   ```
3. Clear checkpoints:
   ```bash
   rm -rf .checkpoints/
   ```
4. Start fresh run:
   ```bash
   python -m planalign_orchestrator.cli run --years 2025-2030
   ```

## Targeted Fixes
- Single model rebuild: `dbt run --select MODEL_NAME`
- Skip to specific year: `dbt run --vars "{'start_year': 2027}"`
- Test single year: `python -m planalign_orchestrator.cli run --years 2025-2025`
```

**Verify:**
- Kill a run mid-year, verify `--resume` skips completed years
- Intentionally break a model, fix using recovery guide

---

## Day 5 (Friday): Prove It Works
**Goal:** Tests that catch real issues

### Morning (2 hours)
```python
# tests/test_production.py
def test_single_year_smoke():
    """Basic sanity - can we run at all?"""
    result = run_simulation("2025-2025")
    assert result['status'] == 'success'
    assert result['workforce_count'] > 0
    assert result['errors'] == []

def test_deterministic_run():
    """Same input = same output"""
    # Run twice with same seed
    result1 = run_simulation("2025-2025", seed=42)
    result2 = run_simulation("2025-2025", seed=42)

    assert result1['workforce_count'] == result2['workforce_count']
    assert result1['total_comp'] == result2['total_comp']

def test_business_metrics():
    """Do the numbers make business sense?"""
    result = run_simulation("2025-2026")

    # Growth happened if configured
    if config.get('growth_rate', 0) > 0:
        assert result['2026']['workforce'] > result['2025']['workforce']

    # Contributions exist if deferral > 0
    if config.get('default_deferral_rate', 0) > 0:
        assert result['2026']['total_contributions'] > 0

    # No crazy outliers
    assert 0.5 < result['2026']['workforce'] / result['2025']['workforce'] < 2.0

def test_resume_after_failure():
    """Can we recover from crashes?"""
    # Run year 1
    run_simulation("2025-2025")
    year1_count = get_workforce_count(2025)

    # Simulate crash, then resume
    run_simulation("2025-2027", resume=True)

    # Year 1 shouldn't change
    assert get_workforce_count(2025) == year1_count

    # Later years should exist
    assert get_workforce_count(2027) > 0
```

### Afternoon (2 hours)
```bash
# Create quick validation script
cat > validate_production.sh << 'EOF'
#!/bin/bash
echo "=== Production Validation ==="

# 1. Environment check
echo "✓ Checking environment..."
python -c "import os; assert os.getenv('GEMINI_API_KEY'), 'Missing API key'"

# 2. Run tests
echo "✓ Running tests..."
pytest tests/test_production.py -v

# 3. Data quality
echo "✓ Checking data quality..."
dbt test --select tag:critical

# 4. Performance check
echo "✓ Testing performance..."
time python -m planalign_orchestrator.cli run --years 2025-2025

echo "=== All checks passed! ==="
EOF

chmod +x validate_production.sh
./validate_production.sh
```

**Verify:** All tests green, single year runs in <60 seconds

---

## Weekend: Only If Something's Actually Broken

### If it's too slow (>5 min per year):
```sql
-- Run EXPLAIN ANALYZE on the slowest query from logs
EXPLAIN ANALYZE SELECT ... FROM [slowest_model];
-- Add ONE index based on results
CREATE INDEX IF NOT EXISTS idx_critical ON table(column);
```

### If tests keep failing:
- Add `--seed 42` to make runs deterministic
- Reduce test data size for faster iteration

---

## What We Added (and Why)

✅ **Day 0 baseline** - Know what "working" looks like before changing
✅ **Run IDs** - Track everything from one run together
✅ **Better backups** - Atomic, versioned, with cleanup
✅ **Config validation** - Fail fast on missing env vars
✅ **Checkpoint hashing** - Don't skip years if config changed
✅ **Failing row details** - See exactly what broke, not just counts
✅ **Business metric tests** - Catch "technically works but wrong" issues
✅ **Deterministic mode** - Reproducible failures

## What We Still Don't Need

❌ Prometheus/Grafana
❌ Circuit breakers
❌ Async operations
❌ 100% test coverage
❌ Perfect documentation
❌ Performance optimization (unless actually slow)

## Start Right Now

```bash
# 1. Day 0 - Capture baseline (5 minutes)
python -m planalign_orchestrator.cli run --years 2025-2025
cp dbt/simulation.duckdb dbt/baseline.duckdb

# 2. Create structure (2 minutes)
mkdir -p dbt/backups logs artifacts/runs .checkpoints

# 3. Add .env (2 minutes)
echo "GEMINI_API_KEY=${GEMINI_API_KEY}" > .env
echo "DB_PATH=dbt/simulation.duckdb" >> .env

# 4. Test backup function (1 minute)
python -c "from your_code import create_backup; print(create_backup())"
```

This plan keeps the pragmatic focus while adding the genuinely useful improvements from the feedback. Each addition directly prevents a real production issue you've likely already hit.
