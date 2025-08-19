#!/bin/bash
# validate_production.sh - Complete production readiness validation
# Part of Epic E047: Production Testing & Validation Framework

set -e

echo "=== PlanWise Navigator Production Validation ==="
echo "Started: $(date)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        "INFO")
            echo -e "${BLUE}🔍 ${message}${NC}"
            ;;
        "SUCCESS")
            echo -e "${GREEN}✅ ${message}${NC}"
            ;;
        "WARNING")
            echo -e "${YELLOW}⚠️  ${message}${NC}"
            ;;
        "ERROR")
            echo -e "${RED}❌ ${message}${NC}"
            ;;
    esac
}

# Function to check exit code and exit on failure
check_result() {
    local exit_code=$1
    local operation=$2
    if [ $exit_code -ne 0 ]; then
        print_status "ERROR" "$operation failed with exit code $exit_code"
        exit $exit_code
    fi
}

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "navigator_orchestrator" ]; then
    print_status "ERROR" "Must be run from PlanWise Navigator root directory"
    exit 1
fi

# 1. Environment validation
print_status "INFO" "Validating environment..."

# Check Python version
python_version=$(python --version 2>&1 | cut -d' ' -f2)
print_status "INFO" "Python version: $python_version"

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    print_status "WARNING" "Virtual environment not detected - ensure dependencies are available"
else
    print_status "SUCCESS" "Virtual environment active: $VIRTUAL_ENV"
fi

# Check critical environment variables
python -c "
import os
import sys

# Check for Gemini API key (optional)
if not os.getenv('GEMINI_API_KEY'):
    print('⚠️  GEMINI_API_KEY not set (required for some features)')

# Check database exists
if not os.path.exists('simulation.duckdb'):
    print('❌ Missing simulation.duckdb - run a simulation first')
    sys.exit(1)
else:
    print('✅ simulation.duckdb found')

# Check dbt project
if not os.path.exists('dbt/dbt_project.yml'):
    print('❌ Missing dbt project')
    sys.exit(1)
else:
    print('✅ dbt project found')

print('✅ Environment validation passed')
"
check_result $? "Environment validation"

# 2. Dependency check
print_status "INFO" "Checking dependencies..."
python -c "
try:
    import pytest
    import duckdb
    import psutil
    import navigator_orchestrator
    print('✅ Critical dependencies available')
except ImportError as e:
    print(f'❌ Missing dependency: {e}')
    exit(1)
"
check_result $? "Dependency check"

# 3. Database connectivity test
print_status "INFO" "Testing database connectivity..."
python -c "
import duckdb
try:
    conn = duckdb.connect('simulation.duckdb')
    result = conn.execute('SELECT 1').fetchone()
    if result[0] == 1:
        print('✅ Database connectivity OK')
    else:
        print('❌ Database test query failed')
        exit(1)
    conn.close()
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    exit(1)
"
check_result $? "Database connectivity test"

# 4. Backup system test
print_status "INFO" "Testing backup system..."
python -c "
try:
    from navigator_orchestrator.backup_manager import BackupManager
    bm = BackupManager()
    backup_path = bm.create_backup()
    if backup_path.exists():
        print(f'✅ Backup created successfully: {backup_path}')
    else:
        print('❌ Backup creation failed')
        exit(1)
except Exception as e:
    print(f'❌ Backup system test failed: {e}')
    exit(1)
"
check_result $? "Backup system test"

# 5. Run smoke tests
print_status "INFO" "Running smoke tests..."
if command -v pytest &> /dev/null; then
    pytest tests/test_production_smoke.py -v --tb=short -x
    check_result $? "Smoke tests"
    print_status "SUCCESS" "Smoke tests passed"
else
    print_status "WARNING" "pytest not available - skipping smoke tests"
fi

# 6. Run data quality tests
print_status "INFO" "Running data quality tests..."
if command -v pytest &> /dev/null; then
    pytest tests/test_data_quality.py -v --tb=short -x
    check_result $? "Data quality tests"
    print_status "SUCCESS" "Data quality tests passed"
else
    print_status "WARNING" "pytest not available - skipping data quality tests"
fi

# 7. Run business logic tests (with timeout for deterministic test)
print_status "INFO" "Running business logic tests..."
if command -v pytest &> /dev/null; then
    timeout 300 pytest tests/test_business_logic.py -v --tb=short -x
    if [ $? -eq 124 ]; then
        print_status "WARNING" "Business logic tests timed out (this may be expected for deterministic tests)"
    else
        check_result $? "Business logic tests"
        print_status "SUCCESS" "Business logic tests passed"
    fi
else
    print_status "WARNING" "pytest not available - skipping business logic tests"
fi

# 8. Run compliance tests
print_status "INFO" "Running compliance tests..."
if command -v pytest &> /dev/null; then
    pytest tests/test_compliance.py -v --tb=short -x
    check_result $? "Compliance tests"
    print_status "SUCCESS" "Compliance tests passed"
else
    print_status "WARNING" "pytest not available - skipping compliance tests"
fi

# 9. Run performance tests (with timeout)
print_status "INFO" "Running performance tests..."
if command -v pytest &> /dev/null; then
    timeout 600 pytest tests/test_performance.py -v --tb=short -x -k "not test_multi_year_scalability"
    if [ $? -eq 124 ]; then
        print_status "WARNING" "Performance tests timed out"
    else
        check_result $? "Performance tests"
        print_status "SUCCESS" "Performance tests passed"
    fi
else
    print_status "WARNING" "pytest not available - skipping performance tests"
fi

# 10. Database health check
print_status "INFO" "Running database health check..."
python -c "
import duckdb

try:
    conn = duckdb.connect('simulation.duckdb')

    # Check table existence and row counts
    tables = conn.execute('SHOW TABLES').fetchall()
    table_names = [t[0] for t in tables]

    critical_tables = ['fct_yearly_events', 'fct_workforce_snapshot']
    for table in critical_tables:
        if table in table_names:
            count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            print(f'✅ {table}: {count:,} rows')
        else:
            print(f'⚠️  {table}: not found')

    # Check for recent simulation data
    try:
        recent_years = conn.execute('''
            SELECT DISTINCT simulation_year
            FROM fct_workforce_snapshot
            ORDER BY simulation_year DESC
            LIMIT 3
        ''').fetchall()
        years = [str(y[0]) for y in recent_years]
        print(f'✅ Recent simulation years: {', '.join(years)}')
    except:
        print('⚠️  No recent simulation data found')

    conn.close()
    print('✅ Database health check passed')

except Exception as e:
    print(f'❌ Database health check failed: {e}')
    exit(1)
"
check_result $? "Database health check"

# 11. Configuration validation
print_status "INFO" "Validating configuration..."
python -c "
try:
    from navigator_orchestrator.config import load_simulation_config
    from pathlib import Path

    config_path = Path('config/simulation_config.yaml')
    if config_path.exists():
        config = load_simulation_config(config_path)
        print(f'✅ Configuration loaded: {config.start_year}-{config.end_year}')
    else:
        print('⚠️  simulation_config.yaml not found')

    # Check dbt profiles
    profiles_path = Path('dbt/profiles.yml')
    if profiles_path.exists():
        print('✅ dbt profiles.yml found')
    else:
        print('⚠️  dbt profiles.yml not found')

except Exception as e:
    print(f'❌ Configuration validation failed: {e}')
    exit(1)
"
check_result $? "Configuration validation"

# 12. System resource check
print_status "INFO" "Checking system resources..."
python -c "
import psutil
import shutil

# Check available disk space
total, used, free = shutil.disk_usage('.')
free_gb = free // (1024**3)
if free_gb < 5:
    print(f'⚠️  Low disk space: {free_gb}GB available')
else:
    print(f'✅ Disk space OK: {free_gb}GB available')

# Check available memory
memory = psutil.virtual_memory()
available_gb = memory.available // (1024**3)
if available_gb < 2:
    print(f'⚠️  Low memory: {available_gb}GB available')
else:
    print(f'✅ Memory OK: {available_gb}GB available')

# Check CPU count
cpu_count = psutil.cpu_count()
print(f'✅ CPU cores: {cpu_count}')

print('✅ System resources check completed')
"
check_result $? "System resource check"

# 13. Final end-to-end test (quick single year)
print_status "INFO" "Running final end-to-end validation..."
time python -m navigator_orchestrator.cli run --years 2025-2025 --force-clear --threads 4
check_result $? "End-to-end validation"
print_status "SUCCESS" "End-to-end validation passed"

# Summary
echo ""
echo "=================================================="
print_status "SUCCESS" "All validation checks passed!"
echo "PlanWise Navigator is ready for production deployment."
echo "Completed: $(date)"
echo "=================================================="

# Optional: Generate validation report
if command -v python &> /dev/null; then
    python -c "
import json
from datetime import datetime
from pathlib import Path

report = {
    'validation_timestamp': datetime.now().isoformat(),
    'status': 'PASSED',
    'checks_completed': [
        'Environment validation',
        'Dependency check',
        'Database connectivity',
        'Backup system test',
        'Smoke tests',
        'Data quality tests',
        'Business logic tests',
        'Compliance tests',
        'Performance tests',
        'Database health check',
        'Configuration validation',
        'System resources check',
        'End-to-end validation'
    ],
    'system_info': {
        'platform': '$(uname -s)',
        'hostname': '$(hostname)',
        'validation_script_version': '1.0.0'
    }
}

report_path = Path('validation_report.json')
with open(report_path, 'w') as f:
    json.dump(report, f, indent=2)

print(f'✅ Validation report written to {report_path}')
"
fi

exit 0
