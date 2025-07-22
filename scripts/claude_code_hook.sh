#!/bin/bash
# Claude Code Pre-Command Hook for PlanWise Navigator
#
# This hook intercepts bash commands before execution to:
# 1. Validate environment setup
# 2. Set up correct working directories
# 3. Activate virtual environment when needed
# 4. Prevent trial-and-error command execution
#
# This script is designed to be called as a Claude Code hook.

set -e  # Exit on error

# Configuration
PROJECT_ROOT="/Users/nicholasamaral/planwise_navigator"
SMART_WRAPPER="$PROJECT_ROOT/scripts/smart_command_wrapper.py"
LOG_FILE="$PROJECT_ROOT/claude_code_hook.log"
VERBOSE="${CLAUDE_HOOK_VERBOSE:-false}"

# Function to log messages
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $level: $message" >> "$LOG_FILE"

    if [[ "$VERBOSE" == "true" ]]; then
        echo "🔧 Hook $level: $message" >&2
    fi
}

# Function to check if command should be intercepted
should_intercept() {
    local command="$1"

    # Commands that benefit from smart environment setup
    local intercept_patterns=(
        "^dbt "
        "^dagster "
        "^streamlit "
        "^python.*\.py"
        "^pytest"
        "^pip install"
        "source.*venv.*activate"
        "cd.*dbt.*&&.*dbt"
        "venv/bin/"
    )

    for pattern in "${intercept_patterns[@]}"; do
        if [[ $command =~ $pattern ]]; then
            return 0  # Should intercept
        fi
    done

    return 1  # Don't intercept
}

# Function to detect common problematic patterns
detect_problematic_patterns() {
    local command="$1"
    local issues=()

    # Pattern: trying to cd to dbt directory and run dbt commands
    if [[ $command =~ cd.*dbt.*&&.*dbt ]]; then
        issues+=("❌ Detected cd + dbt pattern - this often fails due to path issues")
    fi

    # Pattern: source venv activation
    if [[ $command =~ source.*venv.*activate ]]; then
        issues+=("⚠️  Detected venv activation - this is handled automatically")
    fi

    # Pattern: manual path prefixes
    if [[ $command =~ \./venv/bin/ ]] || [[ $command =~ \.\.\/venv/bin/ ]]; then
        issues+=("⚠️  Detected manual venv path - smart wrapper handles this automatically")
    fi

    # Pattern: PYTHONPATH manipulation
    if [[ $command =~ PYTHONPATH.*python ]]; then
        issues+=("⚠️  Detected PYTHONPATH manipulation - may not be necessary with smart wrapper")
    fi

    if [[ ${#issues[@]} -gt 0 ]]; then
        return 0  # Found issues
    fi

    return 1  # No issues
}

# Main hook logic
main() {
    local command="$*"

    log_message "INFO" "Hook called with command: $command"

    # Skip if no command provided
    if [[ -z "$command" ]]; then
        log_message "DEBUG" "No command provided, skipping"
        exit 0
    fi

    # Check if we're in the right project
    if [[ ! -f "$PROJECT_ROOT/CLAUDE.md" ]]; then
        log_message "WARNING" "Not in PlanWise Navigator project directory"
        exit 0
    fi

    # Check if smart wrapper exists
    if [[ ! -f "$SMART_WRAPPER" ]]; then
        log_message "ERROR" "Smart command wrapper not found at $SMART_WRAPPER"
        exit 1
    fi

    # Detect problematic patterns and provide warnings
    if detect_problematic_patterns "$command"; then
        log_message "WARNING" "Detected potentially problematic command pattern"

        if [[ "$VERBOSE" == "true" ]]; then
            echo "🚨 Claude Code Hook Warning:" >&2
            echo "   The command you're trying to run has patterns that often fail." >&2
            echo "   The hook will attempt to fix this automatically." >&2
            echo "   Command: $command" >&2
        fi
    fi

    # Check if we should intercept this command
    if should_intercept "$command"; then
        log_message "INFO" "Intercepting command for smart execution"

        # Validate environment first
        if ! python3 "$SMART_WRAPPER" --validate --working-dir "$PROJECT_ROOT" > /dev/null 2>&1; then
            log_message "ERROR" "Environment validation failed"

            # Show helpful error message
            echo "❌ Environment validation failed!" >&2
            echo "" >&2
            echo "🔧 The smart hook detected that your environment needs setup." >&2
            echo "   Run this command to see setup instructions:" >&2
            echo "   python3 $SMART_WRAPPER --help-setup" >&2
            echo "" >&2
            echo "🚫 Blocking command execution to prevent trial-and-error failures." >&2

            exit 1
        fi

        log_message "INFO" "Environment validated, executing with smart wrapper"

        # Execute with smart wrapper
        if [[ "$VERBOSE" == "true" ]]; then
            echo "✅ Smart hook executing: $command" >&2
            python3 "$SMART_WRAPPER" "$command" --verbose --working-dir "$PROJECT_ROOT"
        else
            python3 "$SMART_WRAPPER" "$command" --working-dir "$PROJECT_ROOT"
        fi

        local exit_code=$?
        log_message "INFO" "Command completed with exit code $exit_code"
        exit $exit_code

    else
        log_message "DEBUG" "Command not intercepted, allowing normal execution"
        exit 0  # Allow normal execution
    fi
}

# Handle different invocation methods
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Called directly as a script
    main "$@"
else
    # Sourced or called in other ways
    main "$@"
fi
