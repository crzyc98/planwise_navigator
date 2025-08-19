#!/bin/bash
# run_production_tests.sh - Quick production test runner
# Part of Epic E047: Production Testing & Validation Framework

set -e

echo "=== PlanWise Navigator Production Test Runner ==="
echo "Started: $(date)"

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}🔍 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "navigator_orchestrator" ]; then
    echo "❌ Must be run from PlanWise Navigator root directory"
    exit 1
fi

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Please install dependencies: pip install -r requirements.txt"
    exit 1
fi

# Parse command line arguments
CATEGORY="${1:-all}"
VERBOSE="${2:-false}"

# Set pytest options based on arguments
PYTEST_OPTS="-v --tb=short"
if [ "$VERBOSE" = "true" ] || [ "$VERBOSE" = "-v" ]; then
    PYTEST_OPTS="-vv --tb=long"
fi

case $CATEGORY in
    "smoke")
        print_info "Running smoke tests only..."
        pytest tests/test_production_smoke.py $PYTEST_OPTS
        ;;
    "data-quality")
        print_info "Running data quality tests only..."
        pytest tests/test_data_quality.py $PYTEST_OPTS
        ;;
    "business-logic")
        print_info "Running business logic tests only..."
        pytest tests/test_business_logic.py $PYTEST_OPTS
        ;;
    "compliance")
        print_info "Running compliance tests only..."
        pytest tests/test_compliance.py $PYTEST_OPTS
        ;;
    "performance")
        print_info "Running performance tests only..."
        pytest tests/test_performance.py $PYTEST_OPTS
        ;;
    "fast")
        print_info "Running fast tests (smoke + data quality)..."
        pytest tests/test_production_smoke.py tests/test_data_quality.py $PYTEST_OPTS
        ;;
    "all")
        print_info "Running all production tests..."
        pytest tests/test_production_smoke.py tests/test_data_quality.py tests/test_business_logic.py tests/test_compliance.py tests/test_performance.py $PYTEST_OPTS
        ;;
    *)
        echo "Usage: $0 [category] [verbose]"
        echo ""
        echo "Categories:"
        echo "  smoke          - Quick smoke tests (<60s)"
        echo "  data-quality   - Data quality validation tests"
        echo "  business-logic - Business logic and deterministic tests"
        echo "  compliance     - Regulatory compliance tests"
        echo "  performance    - Performance and load tests"
        echo "  fast           - Smoke + data quality tests"
        echo "  all            - All production tests (default)"
        echo ""
        echo "Verbose: true/false or -v (default: false)"
        echo ""
        echo "Examples:"
        echo "  $0 smoke"
        echo "  $0 fast true"
        echo "  $0 all -v"
        exit 1
        ;;
esac

if [ $? -eq 0 ]; then
    print_success "Production tests completed successfully!"
else
    echo "❌ Some tests failed. Check output above for details."
    exit 1
fi

echo "Completed: $(date)"
