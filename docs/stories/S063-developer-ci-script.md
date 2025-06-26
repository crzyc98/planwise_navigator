# Story S063: Developer-Initiated CI Script

## Story Overview

**Story ID**: S063
**Epic**: E014 - Layered Defense Strategy
**Story Points**: 5
**Priority**: Must Have
**Sprint**: 8
**Status**: Not Started

## User Story

**As a** data developer
**I want** to be able to manually run a comprehensive CI script locally
**So that** I can quickly validate my changes before committing and pushing code

## Background

Currently, developers have no systematic way to validate their changes before committing. This leads to:
- Broken dbt compilation reaching version control
- Failed tests discovered late in the process
- Time wasted on avoidable debugging cycles
- Inconsistent validation practices across team members

## Acceptance Criteria

1. **Script Existence and Accessibility**
   - Script exists at `./scripts/run_ci_tests.sh` and is executable
   - Can be run from project root directory
   - Works on both macOS and Linux environments

2. **Comprehensive Validation Coverage**
   - Includes dbt compilation checks for all models
   - Runs dbt tests (excluding slow/long-running tests)
   - Performs Python linting and type checking
   - Validates critical model functionality

3. **Developer Experience**
   - Provides clear pass/fail feedback with actionable error messages
   - Completes in under 2 minutes for developer productivity
   - Colored output for easy readability (✅ green success, ❌ red failure)
   - Summary report at end showing what passed/failed

4. **Documentation and Usability**
   - Usage documentation added to README.md
   - Clear error messages guide developers to fixes
   - Exit codes support integration with git hooks

5. **Integration Ready**
   - Script can be called by pre-commit hooks
   - Supports environment variable configuration
   - Can run in CI/CD pipeline environment

## Technical Implementation

### Script Structure
```bash
#!/bin/bash
# CI/CD test suite for PlanWise Navigator
set -e  # Exit on error

echo "🔍 Running PlanWise Navigator CI Tests..."

# 1. Python validation
echo "📝 Running Python linting..."
python -m pylint orchestrator/ --fail-under=8.0

# 2. dbt compilation
echo "🔧 Checking dbt compilation..."
cd dbt && dbt compile

# 3. Fast dbt tests
echo "🧪 Running dbt tests..."
dbt test --exclude tag:slow

# 4. Critical model validation
echo "🏗️ Testing critical models..."
dbt run --select tag:critical --vars '{simulation_year: 2025}'

# 5. Data quality checks
echo "✅ Running data quality validation..."
dbt run --select dq_employee_id_validation

echo "✅ All CI tests passed!"
```

### Error Handling
- Capture and display both stdout and stderr
- Provide specific guidance for common failures
- Non-zero exit codes on any failure
- Option to continue on non-critical failures

## Testing Strategy

### Unit Testing
- Test script execution in clean environment
- Validate proper error handling for common failure scenarios
- Test with various dbt project states

### Integration Testing
- Run against known-good codebase (should pass)
- Run against intentionally broken code (should fail gracefully)
- Validate performance requirements (<2 minutes)

## Definition of Done

- [ ] Script created and tested in local environment
- [ ] All acceptance criteria validated
- [ ] Performance requirement met (<2 minutes execution)
- [ ] Documentation added to README.md
- [ ] Script tested by at least one other team member
- [ ] Error scenarios tested and handled gracefully

## Dependencies

- **dbt version**: Compatible with current 1.8.8
- **Python environment**: Requires pylint and mypy packages
- **Shell environment**: Bash 4.0+ for script execution

## Risks and Mitigation

### Risk: Performance Issues
- **Mitigation**: Exclude slow tests, use parallel execution where possible
- **Fallback**: Provide fast/full modes for different use cases

### Risk: Environment Differences
- **Mitigation**: Use relative paths, avoid system-specific commands
- **Testing**: Validate on multiple developer machines

### Risk: Flaky Tests
- **Mitigation**: Identify and exclude unreliable tests initially
- **Improvement**: Add retry logic for known flaky operations

## Success Metrics

- **Developer Adoption**: >80% of team uses script regularly
- **Commit Quality**: Reduction in failed CI builds after implementation
- **Time Savings**: Developers catch issues locally vs. in CI/CD pipeline
- **Developer Satisfaction**: Positive feedback on tool usefulness

## Future Enhancements

- Integration with IDE/editor workflows
- Parallel test execution for improved performance
- Customizable test suites (fast/thorough/critical-only)
- Integration with git hooks for automatic execution

---

*This story provides the foundation for all subsequent testing and validation improvements in Epic E014.*
