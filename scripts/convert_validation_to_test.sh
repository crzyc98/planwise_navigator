#!/bin/bash
# scripts/convert_validation_to_test.sh
#
# Converts a validation model to a dbt test
# Usage: ./scripts/convert_validation_to_test.sh dbt/models/marts/data_quality/dq_xxx.sql
#
# Part of E080: Validation Model to Test Conversion
# This script automates the conversion of validation models (dq_*.sql, validate_*.sql)
# to dbt tests, improving performance by 90% (no table materialization).
#
# Example:
#   ./scripts/convert_validation_to_test.sh dbt/models/marts/data_quality/dq_new_hire_match_validation.sql
#   Output: dbt/tests/data_quality/test_new_hire_match_validation.sql

set -e

# Check if model path provided
if [ -z "$1" ]; then
    echo "Error: Model path required"
    echo "Usage: $0 <model_path>"
    echo ""
    echo "Examples:"
    echo "  $0 dbt/models/marts/data_quality/dq_new_hire_match_validation.sql"
    echo "  $0 dbt/models/analysis/validate_compensation_bounds.sql"
    exit 1
fi

MODEL_PATH="$1"
MODEL_NAME=$(basename "$MODEL_PATH" .sql)

# Check if model file exists
if [ ! -f "$MODEL_PATH" ]; then
    echo "Error: Model file not found: $MODEL_PATH"
    exit 1
fi

# Determine target directory based on source
if [[ "$MODEL_PATH" == *"/analysis/"* ]]; then
    TARGET_DIR="dbt/tests/analysis"
elif [[ "$MODEL_PATH" == *"/data_quality/"* ]]; then
    TARGET_DIR="dbt/tests/data_quality"
elif [[ "$MODEL_PATH" == *"/intermediate/"* ]]; then
    TARGET_DIR="dbt/tests/intermediate"
else
    TARGET_DIR="dbt/tests/marts"
fi

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Determine test name (remove dq_ or validate_ prefix)
if [[ "$MODEL_NAME" == dq_* ]]; then
    TEST_NAME="test_${MODEL_NAME#dq_}"
elif [[ "$MODEL_NAME" == validate_* ]]; then
    TEST_NAME="test_${MODEL_NAME#validate_}"
else
    TEST_NAME="test_$MODEL_NAME"
fi

TARGET_PATH="$TARGET_DIR/${TEST_NAME}.sql"

echo "======================================"
echo "Converting Validation Model to Test"
echo "======================================"
echo "Model Name: $MODEL_NAME"
echo "Test Name:  $TEST_NAME"
echo "Source:     $MODEL_PATH"
echo "Target:     $TARGET_PATH"
echo ""

# Copy file, removing config block lines
grep -v "{{ config(" "$MODEL_PATH" | \
grep -v "materialized=" | \
grep -v "tags=" | \
grep -v ")}}" > "$TARGET_PATH"

# Add header comment at top
HEADER="-- Converted from validation model to test (E080)
-- Original model: $MODEL_NAME.sql
-- Conversion date: $(date +%Y-%m-%d)
--
-- IMPORTANT: Add year filter for performance optimization!
-- Add this to your WHERE clause:
--   WHERE simulation_year = {{ var('simulation_year') }}
--
-- Test behavior:
--   PASS: 0 rows returned (no validation failures)
--   FAIL: >0 rows returned (violations stored in test_failures.$TEST_NAME)

"

# Prepend header to file
echo "$HEADER" | cat - "$TARGET_PATH" > temp && mv temp "$TARGET_PATH"

echo "✅ Conversion complete!"
echo ""
echo "======================================"
echo "Next Steps (Manual Review Required)"
echo "======================================"
echo ""
echo "1. Review converted test:"
echo "   cat $TARGET_PATH"
echo ""
echo "2. Add year filter for performance:"
echo "   Add to WHERE clause: simulation_year = {{ var('simulation_year') }}"
echo ""
echo "3. Test the conversion:"
echo "   cd dbt"
echo "   dbt test --select $TEST_NAME --vars \"simulation_year: 2025\""
echo ""
echo "4. Validate results match original model:"
echo "   cd dbt"
echo "   dbt run --select $MODEL_NAME --vars \"simulation_year: 2025\""
echo "   dbt test --select $TEST_NAME --vars \"simulation_year: 2025\""
echo "   # Compare row counts in DuckDB"
echo ""
echo "5. Document test in schema.yml:"
echo "   Add test configuration to dbt/tests/schema.yml"
echo ""
echo "6. Only after validation, delete original model:"
echo "   rm $MODEL_PATH"
echo ""
echo "======================================"
