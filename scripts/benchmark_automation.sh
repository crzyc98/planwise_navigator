#!/bin/bash
set -euo pipefail

# Event Generation Benchmark Automation Script
#
# Provides automated benchmark execution with various modes:
# - Daily performance monitoring
# - Release gate validation
# - Regression detection
# - Performance baseline updates
#
# Usage:
#   ./scripts/benchmark_automation.sh --help
#   ./scripts/benchmark_automation.sh daily-monitor
#   ./scripts/benchmark_automation.sh release-gate --target-time 60
#   ./scripts/benchmark_automation.sh regression-check --fail-on-regression

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BENCHMARK_SCRIPT="$SCRIPT_DIR/benchmark_event_generation.py"
CI_SCRIPT="$SCRIPT_DIR/benchmark_ci_integration.py"

# Default configuration
DEFAULT_OUTPUT_DIR="$PROJECT_ROOT/benchmark_results"
DEFAULT_BASELINE_DIR="$PROJECT_ROOT/benchmark_baselines"
DEFAULT_SCENARIOS="quick 1kx3"
DEFAULT_MODES="sql polars"
DEFAULT_RUNS=3
DEFAULT_TARGET_TIME=60

# Logging setup
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

die() {
    error "$@"
    exit 1
}

# Help function
show_help() {
    cat << EOF
Event Generation Benchmark Automation

USAGE:
    $0 <command> [options]

COMMANDS:
    daily-monitor           Run daily performance monitoring
    release-gate           Run release gate performance validation
    regression-check       Check for performance regressions
    baseline-update        Update performance baselines
    stress-test           Run comprehensive stress testing
    quick-validate         Quick validation benchmark
    help                  Show this help message

OPTIONS:
    --scenarios LIST      Space-separated list of scenarios (default: $DEFAULT_SCENARIOS)
    --modes LIST          Space-separated list of modes (default: $DEFAULT_MODES)
    --runs N             Number of runs per scenario (default: $DEFAULT_RUNS)
    --target-time N      Target time in seconds for gates (default: $DEFAULT_TARGET_TIME)
    --output-dir DIR     Output directory (default: $DEFAULT_OUTPUT_DIR)
    --baseline-dir DIR   Baseline directory (default: $DEFAULT_BASELINE_DIR)
    --fail-on-regression Fail on performance regression (default: true)
    --no-fail-on-regression  Do not fail on regression
    --verbose            Verbose output
    --quiet              Minimal output
    --dry-run            Show commands without executing

EXAMPLES:
    # Daily monitoring with default scenarios
    $0 daily-monitor

    # Release gate with strict timing
    $0 release-gate --target-time 45 --scenarios 5kx5

    # Regression check without failing CI
    $0 regression-check --no-fail-on-regression

    # Update baselines after optimization
    $0 baseline-update --scenarios "quick 1kx3 5kx5"

    # Stress test all scenarios
    $0 stress-test --runs 5

ENVIRONMENT VARIABLES:
    BENCHMARK_OUTPUT_DIR   Override default output directory
    BENCHMARK_BASELINE_DIR Override default baseline directory
    BENCHMARK_SCENARIOS    Override default scenarios
    BENCHMARK_MODES        Override default modes
    CI                    Set to 'true' for CI mode
    BUILD_NUMBER          Build number for tracking
    GIT_COMMIT            Git commit for tracking
EOF
}

# Parse command line arguments
parse_args() {
    COMMAND=""
    SCENARIOS="${BENCHMARK_SCENARIOS:-$DEFAULT_SCENARIOS}"
    MODES="${BENCHMARK_MODES:-$DEFAULT_MODES}"
    RUNS=$DEFAULT_RUNS
    TARGET_TIME=$DEFAULT_TARGET_TIME
    OUTPUT_DIR="${BENCHMARK_OUTPUT_DIR:-$DEFAULT_OUTPUT_DIR}"
    BASELINE_DIR="${BENCHMARK_BASELINE_DIR:-$DEFAULT_BASELINE_DIR}"
    FAIL_ON_REGRESSION=true
    VERBOSE=false
    QUIET=false
    DRY_RUN=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            daily-monitor|release-gate|regression-check|baseline-update|stress-test|quick-validate|help)
                COMMAND="$1"
                shift
                ;;
            --scenarios)
                SCENARIOS="$2"
                shift 2
                ;;
            --modes)
                MODES="$2"
                shift 2
                ;;
            --runs)
                RUNS="$2"
                shift 2
                ;;
            --target-time)
                TARGET_TIME="$2"
                shift 2
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --baseline-dir)
                BASELINE_DIR="$2"
                shift 2
                ;;
            --fail-on-regression)
                FAIL_ON_REGRESSION=true
                shift
                ;;
            --no-fail-on-regression)
                FAIL_ON_REGRESSION=false
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --quiet)
                QUIET=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                die "Unknown option: $1"
                ;;
        esac
    done

    if [[ -z "$COMMAND" ]]; then
        die "No command specified. Use --help for usage information."
    fi
}

# Utility functions
check_prerequisites() {
    log "Checking prerequisites..."

    # Check Python environment
    if ! command -v python3 &> /dev/null; then
        die "Python3 is required but not installed"
    fi

    # Check required Python packages
    python3 -c "import numpy, scipy, psutil" 2>/dev/null || {
        die "Required Python packages not installed. Run: pip install numpy scipy psutil"
    }

    # Check benchmark scripts exist
    if [[ ! -f "$BENCHMARK_SCRIPT" ]]; then
        die "Benchmark script not found: $BENCHMARK_SCRIPT"
    fi

    if [[ ! -f "$CI_SCRIPT" ]]; then
        die "CI integration script not found: $CI_SCRIPT"
    fi

    # Create output directories
    mkdir -p "$OUTPUT_DIR" "$BASELINE_DIR"

    log "Prerequisites check passed"
}

execute_command() {
    local cmd="$1"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: $cmd"
        return 0
    fi

    if [[ "$VERBOSE" == "true" ]]; then
        log "Executing: $cmd"
    fi

    eval "$cmd"
}

build_benchmark_args() {
    local base_args=""

    # Add common arguments
    base_args+=" --output-dir '$OUTPUT_DIR'"
    base_args+=" --runs $RUNS"

    if [[ "$VERBOSE" == "true" ]]; then
        base_args+=" --verbose"
    elif [[ "$QUIET" == "true" ]]; then
        base_args+=" --quiet"
    fi

    echo "$base_args"
}

build_ci_args() {
    local base_args=""

    # Add common CI arguments
    base_args+=" --baseline-dir '$BASELINE_DIR'"
    base_args+=" --output-dir '$OUTPUT_DIR'"

    if [[ "$FAIL_ON_REGRESSION" == "true" ]]; then
        base_args+=" --fail-on-regression"
    else
        base_args+=" --no-fail-on-regression"
    fi

    if [[ "$VERBOSE" == "true" ]]; then
        base_args+=" --verbose"
    elif [[ "$QUIET" == "true" ]]; then
        base_args+=" --quiet"
    fi

    echo "$base_args"
}

# Command implementations
run_daily_monitor() {
    log "Starting daily performance monitoring..."

    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local daily_output_dir="$OUTPUT_DIR/daily_$timestamp"

    # Run benchmark with monitoring scenarios
    local scenarios="${SCENARIOS:-quick 1kx3}"
    local benchmark_args="$(build_benchmark_args)"
    benchmark_args+=" --scenarios $scenarios"
    benchmark_args+=" --modes $MODES"
    benchmark_args+=" --output-dir '$daily_output_dir'"

    local cmd="python3 '$BENCHMARK_SCRIPT' $benchmark_args"
    execute_command "$cmd"

    # Generate historical comparison if previous results exist
    if [[ -d "$OUTPUT_DIR" ]] && [[ $(find "$OUTPUT_DIR" -name "daily_*" -type d | wc -l) -gt 1 ]]; then
        log "Generating historical performance comparison..."
        # Could add historical analysis here
    fi

    log "Daily monitoring completed. Results in: $daily_output_dir"
}

run_release_gate() {
    log "Running release gate validation..."

    # Use performance gate mode for critical scenario
    local ci_args="$(build_ci_args)"
    ci_args+=" --mode performance-gate"
    ci_args+=" --scenario 5kx5"
    ci_args+=" --target-time $TARGET_TIME"
    ci_args+=" --mode-single polars"

    local cmd="python3 '$CI_SCRIPT' $ci_args"

    if execute_command "$cmd"; then
        log "Release gate PASSED - performance target met"
        return 0
    else
        error "Release gate FAILED - performance target not met"
        return 1
    fi
}

run_regression_check() {
    log "Running performance regression check..."

    local ci_args="$(build_ci_args)"
    ci_args+=" --mode regression-check"

    if [[ -n "$SCENARIOS" ]]; then
        ci_args+=" --scenarios $SCENARIOS"
    fi

    if [[ -n "$MODES" ]]; then
        ci_args+=" --modes $MODES"
    fi

    local cmd="python3 '$CI_SCRIPT' $ci_args"

    if execute_command "$cmd"; then
        log "Regression check PASSED - no significant regressions"
        return 0
    else
        if [[ "$FAIL_ON_REGRESSION" == "true" ]]; then
            error "Regression check FAILED - performance regressions detected"
            return 1
        else
            log "Regression check completed with warnings"
            return 0
        fi
    fi
}

run_baseline_update() {
    log "Updating performance baselines..."

    # Confirm we're on the right branch for baseline updates
    if command -v git &> /dev/null; then
        local current_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
        if [[ "$current_branch" != "main" && "$current_branch" != "master" ]]; then
            log "WARNING: Updating baseline from branch '$current_branch' (not main/master)"
            if [[ "$DRY_RUN" != "true" ]] && [[ "${CI:-}" != "true" ]]; then
                read -p "Continue with baseline update? [y/N]: " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    log "Baseline update cancelled"
                    return 1
                fi
            fi
        fi
    fi

    local ci_args="$(build_ci_args)"
    ci_args+=" --mode baseline-update"

    if [[ -n "$SCENARIOS" ]]; then
        ci_args+=" --scenarios $SCENARIOS"
    else
        ci_args+=" --scenarios quick 1kx3 5kx5"  # Comprehensive scenarios for baseline
    fi

    if [[ -n "$MODES" ]]; then
        ci_args+=" --modes $MODES"
    fi

    local cmd="python3 '$CI_SCRIPT' $ci_args"

    if execute_command "$cmd"; then
        log "Baseline update completed successfully"
        return 0
    else
        error "Baseline update failed"
        return 1
    fi
}

run_stress_test() {
    log "Running comprehensive stress testing..."

    local stress_output_dir="$OUTPUT_DIR/stress_$(date '+%Y%m%d_%H%M%S')"

    # Run all scenarios with more runs for statistical validity
    local benchmark_args="$(build_benchmark_args)"
    benchmark_args+=" --scenarios quick 1kx3 5kx5 stress"
    benchmark_args+=" --modes $MODES"
    benchmark_args+=" --runs 5"  # More runs for stress testing
    benchmark_args+=" --output-dir '$stress_output_dir'"

    local cmd="python3 '$BENCHMARK_SCRIPT' $benchmark_args"

    if execute_command "$cmd"; then
        log "Stress testing completed. Results in: $stress_output_dir"

        # Generate stress test summary
        log "Generating stress test summary..."
        # Could add stress test analysis here

        return 0
    else
        error "Stress testing failed"
        return 1
    fi
}

run_quick_validate() {
    log "Running quick validation benchmark..."

    local quick_output_dir="$OUTPUT_DIR/quick_$(date '+%Y%m%d_%H%M%S')"

    # Quick validation with minimal scenarios
    local benchmark_args="$(build_benchmark_args)"
    benchmark_args+=" --scenarios quick"
    benchmark_args+=" --modes $MODES"
    benchmark_args+=" --runs 1"  # Single run for speed
    benchmark_args+=" --output-dir '$quick_output_dir'"

    local cmd="python3 '$BENCHMARK_SCRIPT' $benchmark_args"

    if execute_command "$cmd"; then
        log "Quick validation completed successfully"
        return 0
    else
        error "Quick validation failed"
        return 1
    fi
}

# Environment setup
setup_environment() {
    log "Setting up environment..."

    # Change to project root
    cd "$PROJECT_ROOT"

    # Set up Python path
    export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

    # CI/CD specific setup
    if [[ "${CI:-}" == "true" ]]; then
        log "Running in CI/CD environment"

        # Set Git information
        export GIT_COMMIT="${GIT_COMMIT:-$(git rev-parse HEAD 2>/dev/null || echo 'unknown')}"
        export BUILD_NUMBER="${BUILD_NUMBER:-${GITHUB_RUN_NUMBER:-unknown}}"

        # CI-optimized settings
        QUIET=true
        if [[ "$COMMAND" == "regression-check" ]]; then
            SCENARIOS="${SCENARIOS:-quick 1kx3}"  # Faster scenarios for CI
            RUNS=3  # Reasonable number for CI
        fi
    fi

    # Set environment variables for benchmark scripts
    export BENCHMARK_OUTPUT_DIR="$OUTPUT_DIR"
    export BENCHMARK_BASELINE_DIR="$BASELINE_DIR"

    log "Environment setup completed"
}

# Cleanup function
cleanup() {
    local exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        error "Benchmark automation failed with exit code $exit_code"

        # Clean up temporary files on failure
        if [[ -n "${TEMP_FILES:-}" ]]; then
            log "Cleaning up temporary files..."
            rm -rf $TEMP_FILES
        fi
    fi

    exit $exit_code
}

# Main execution
main() {
    # Set up signal handlers
    trap cleanup EXIT

    # Parse arguments
    parse_args "$@"

    # Set up environment
    setup_environment

    # Check prerequisites
    check_prerequisites

    log "Starting benchmark automation: $COMMAND"
    log "Configuration:"
    log "  Scenarios: $SCENARIOS"
    log "  Modes: $MODES"
    log "  Runs: $RUNS"
    log "  Output dir: $OUTPUT_DIR"
    log "  Baseline dir: $BASELINE_DIR"

    # Execute command
    case "$COMMAND" in
        daily-monitor)
            run_daily_monitor
            ;;
        release-gate)
            run_release_gate
            ;;
        regression-check)
            run_regression_check
            ;;
        baseline-update)
            run_baseline_update
            ;;
        stress-test)
            run_stress_test
            ;;
        quick-validate)
            run_quick_validate
            ;;
        help)
            show_help
            ;;
        *)
            die "Unknown command: $COMMAND"
            ;;
    esac

    log "Benchmark automation completed successfully"
}

# Run main function with all arguments
main "$@"
