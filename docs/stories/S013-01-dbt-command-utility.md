# Story S013-01: dbt Command Utility Creation

**Epic**: E013 - Dagster Simulation Pipeline Modularization
**Priority**: High
**Estimate**: 3 story points
**Status**: Not Started

## User Story

**As a** PlanWise Navigator developer
**I want** a centralized utility function for executing dbt commands
**So that** I can eliminate repetitive dbt command patterns and standardize error handling

## Background

The current simulation pipeline contains 15+ repetitive dbt command execution blocks with identical patterns for:
- Building command arrays with --vars and --full-refresh flags
- Executing dbt.cli() and waiting for completion
- Checking process return codes and handling errors
- Logging stdout/stderr on failures

This repetition violates DRY principles and makes maintenance difficult when dbt command patterns need to change.

## Acceptance Criteria

### Functional Requirements
1. **Utility Function Creation**
   - [ ] Create `execute_dbt_command(context, command, vars_dict, full_refresh=False, description="")` function
   - [ ] Function accepts OpExecutionContext, command list, variables dictionary, refresh flag, and description
   - [ ] Function returns execution result or raises exception on failure

2. **Command Building**
   - [ ] Automatically construct --vars JSON string from vars_dict parameter
   - [ ] Add --full-refresh flag when full_refresh=True
   - [ ] Support all dbt commands (run, snapshot, build, test)
   - [ ] Preserve exact command structure from existing implementations

3. **Error Handling**
   - [ ] Check for invocation.process is None condition
   - [ ] Validate process.returncode != 0 for failure detection
   - [ ] Capture and log stdout/stderr on failures
   - [ ] Raise descriptive exceptions with command context

4. **Logging Integration**
   - [ ] Log command execution start with description parameter
   - [ ] Include full command string in info logs
   - [ ] Log execution completion with timing information
   - [ ] Maintain existing log message format for compatibility

### Technical Requirements
1. **Function Signature**
```python
def execute_dbt_command(
    context: OpExecutionContext,
    command: List[str],
    vars_dict: Dict[str, Any],
    full_refresh: bool = False,
    description: str = ""
) -> None
```

2. **Error Message Format**
```python
f"Failed to run {' '.join(command)} for {description}. "
f"Exit code: {invocation.process.returncode}\n\n"
f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
```

3. **Integration Points**
   - [ ] Function accessible from all ops in simulator_pipeline.py
   - [ ] Compatible with existing DbtCliResource from context.resources.dbt
   - [ ] No breaking changes to existing op signatures

## Implementation Details

### File Location
- **Primary**: `orchestrator/simulator_pipeline.py` (as utility function)
- **Alternative**: `orchestrator/dbt_utils.py` (if separate module preferred)

### Code Pattern Replacement
**Before (15+ occurrences)**:
```python
invocation = dbt.cli([
    "run", "--select", "model_name",
    "--vars", f"{{simulation_year: {year}}}"
], context=context).wait()

if invocation.process is None or invocation.process.returncode != 0:
    stdout = invocation.get_stdout() or ""
    stderr = invocation.get_stderr() or ""
    error_message = f"Failed to run model_name. Exit code: {invocation.process.returncode}\\n\\nSTDOUT:\\n{stdout}\\n\\nSTDERR:\\n{stderr}"
    raise Exception(error_message)
```

**After (single utility call)**:
```python
execute_dbt_command(
    context,
    ["run", "--select", "model_name"],
    {"simulation_year": year},
    full_refresh,
    "model_name execution"
)
```

### Variables Dictionary Handling
```python
# Input: {"simulation_year": 2025, "random_seed": 42}
# Output: "{simulation_year: 2025, random_seed: 42}"
vars_string = "{" + ", ".join([f"{k}: {v}" for k, v in vars_dict.items()]) + "}"
```

## Testing Requirements

### Unit Tests
1. **Command Construction**
   - [ ] Test basic command building with no variables
   - [ ] Test command with single variable
   - [ ] Test command with multiple variables
   - [ ] Test full_refresh flag addition

2. **Error Handling**
   - [ ] Test behavior when invocation.process is None
   - [ ] Test behavior when returncode != 0
   - [ ] Test exception message format
   - [ ] Test stdout/stderr capture and logging

3. **Edge Cases**
   - [ ] Empty vars_dict handling
   - [ ] Special characters in variable values
   - [ ] Very long command strings
   - [ ] Missing dbt resource scenario

### Integration Tests
1. **Existing Command Replacement**
   - [ ] Replace one existing dbt command call with utility
   - [ ] Verify identical behavior and logging output
   - [ ] Confirm no changes to simulation results

## Definition of Done

- [ ] Utility function implemented and tested
- [ ] At least 3 existing dbt command calls replaced with utility
- [ ] Unit tests written and passing (>95% coverage)
- [ ] Integration test validates identical behavior
- [ ] Code review completed and approved
- [ ] Documentation updated with utility function usage

## Dependencies

- **Upstream**: None
- **Downstream**: S013-03 (Event Processing), S013-05 (Single-Year Refactoring), S013-06 (Multi-Year Transformation)

## Risk Mitigation

1. **Command Format Changes**: Test utility with various dbt command types before full rollout
2. **Logging Compatibility**: Maintain exact log message format to avoid breaking monitoring/alerting
3. **Error Handling Edge Cases**: Comprehensive testing of failure scenarios

---

**Implementation Notes**: Start with non-critical dbt commands for initial testing, then gradually replace all 15+ occurrences across the pipeline.
