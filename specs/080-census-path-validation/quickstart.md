# Implementation Quickstart: Census Path Validation

**Date**: 2026-03-18
**Feature**: Enforce Census Path Validation on Simulation Start
**Branch**: `080-census-path-validation`

## Overview

Replace silent fallback to default census path with hard-fail validation. When a simulation is launched from Studio, the system MUST validate that `census_parquet_path` exists in the merged config and that the file exists on disk.

---

## Key Code Changes

### File 1: `planalign_api/services/simulation/service.py`

**Location**: Lines 404-412 (method `_validate_census`)

**Current Code**:
```python
@staticmethod
def _validate_census(config: Dict[str, Any]) -> None:
    census_path = config.get("setup", {}).get("census_parquet_path")
    if census_path:
        if not Path(census_path).exists():
            raise ValueError(f"Census file not found: {census_path}")
        logger.info(f"Using census file: {census_path}")
    else:
        logger.warning("No census_parquet_path in config - using default")
```

**Changes**:
1. Remove the `else` clause (lines 411-412) that logs a warning and continues
2. Raise `ConfigurationError` instead of `ValueError`
3. Add `ExecutionContext` with scenario_id for audit trail
4. Validate path is non-empty (not whitespace-only)
5. Include actionable error messages per FR-002 and FR-004

**New Code** (pseudocode):
```python
@staticmethod
def _validate_census(config: Dict[str, Any], scenario_id: str = "", workspace_id: str = "") -> None:
    census_path = config.get("setup", {}).get("census_parquet_path")

    # FR-001: Reject if census_parquet_path is absent or empty
    if not census_path or not str(census_path).strip():
        from planalign_orchestrator.exceptions import ConfigurationError, ExecutionContext
        error_msg = "census_parquet_path is required but was not found in the scenario config. Ensure a census file has been uploaded to the scenario folder before running."
        context = ExecutionContext(scenario_id=scenario_id, metadata={"missing_field": "setup.census_parquet_path", "workspace_id": workspace_id})
        raise ConfigurationError(error_msg, context=context, severity=ErrorSeverity.ERROR)

    # FR-003: Validate file exists on filesystem
    census_file = Path(census_path)
    if not census_file.exists():
        from planalign_orchestrator.exceptions import ConfigurationError, ExecutionContext
        error_msg = f"Census file not found at '{census_path}'. Upload a valid census parquet file to the scenario folder and retry."
        context = ExecutionContext(scenario_id=scenario_id, metadata={"expected_path": str(census_path), "workspace_id": workspace_id})
        raise ConfigurationError(error_msg, context=context, severity=ErrorSeverity.ERROR)

    # FR-005: No fallback to default — hard fail only
    logger.info(f"Using census file: {census_path}")
```

**Why this location**: This method is called early in `_prepare_simulation()` before any subprocess launch, enabling fail-fast behavior per FR-001.

---

### File 2: `planalign_orchestrator/error_catalog.py`

**Location**: Add to `_initialize_patterns()` method

**Changes**: Add two error patterns to the catalog for census-related errors.

**New Patterns**:
```python
# Pattern 1: Missing census_parquet_path
self.patterns.append(ErrorPattern(
    pattern=re.compile(r"census_parquet_path is required.*not found.*scenario config"),
    category=ErrorCategory.CONFIGURATION,
    title="Census File Not Configured",
    description="The census parquet file path is required for simulations but was not found in the scenario configuration.",
    resolution_hints=[
        ResolutionHint(
            title="Upload Census File to Scenario",
            description="Add a census parquet file to your scenario before running a simulation.",
            steps=[
                "1. Open PlanAlign Studio",
                "2. Go to your scenario",
                "3. Click 'Upload Files' and select your census.parquet file",
                "4. Verify the file appears in the scenario folder",
                "5. Retry the simulation"
            ],
            documentation_url="https://docs.fidelity.com/planalign/census-upload",
            estimated_resolution_time="2-3 minutes"
        )
    ]
))

# Pattern 2: Census file not found on disk
self.patterns.append(ErrorPattern(
    pattern=re.compile(r"Census file not found at.*Upload a valid census parquet"),
    category=ErrorCategory.CONFIGURATION,
    title="Census File Missing or Moved",
    description="The census parquet file referenced in the config does not exist at the expected path.",
    resolution_hints=[
        ResolutionHint(
            title="Verify Census File Location",
            description="Check that the census parquet file exists at the configured path.",
            steps=[
                "1. Check the error message for the expected file path",
                "2. Verify the census.parquet file exists at that location",
                "3. If the file was moved or deleted, re-upload it via Studio",
                "4. If the path is incorrect, update it in scenario settings",
                "5. Retry the simulation"
            ],
            documentation_url="https://docs.fidelity.com/planalign/census-troubleshooting",
            estimated_resolution_time="1-2 minutes"
        )
    ]
))
```

**Why this location**: Centralized error catalog enables consistent error handling across the codebase and provides self-service diagnostics.

---

### File 3: `tests/test_census_validation.py` (NEW)

**Purpose**: Test `_validate_census()` validation logic

**Test Cases** (Red-Green-Refactor order):
1. Test missing key: `census_parquet_path` not in config → ConfigurationError
2. Test empty string: `census_parquet_path: ""` → ConfigurationError
3. Test whitespace: `census_parquet_path: "   "` → ConfigurationError
4. Test missing file: Path exists in config but file doesn't → ConfigurationError
5. Test valid path: File exists and is readable → No error (success)
6. Test error message format: Error includes actionable guidance
7. Test context: Error includes scenario_id and correlation_id

**Example Test Structure**:
```python
import pytest
from pathlib import Path
from planalign_api.services.simulation.service import SimulationService
from planalign_orchestrator.exceptions import ConfigurationError

def test_validate_census_missing_key():
    """Test that missing census_parquet_path raises ConfigurationError"""
    config = {"setup": {}}  # No census_parquet_path key

    with pytest.raises(ConfigurationError) as exc_info:
        SimulationService._validate_census(config, scenario_id="test_scenario", workspace_id="test_workspace")

    assert "census_parquet_path is required" in str(exc_info.value)
    assert exc_info.value.context.scenario_id == "test_scenario"

def test_validate_census_empty_string(tmp_path):
    """Test that empty census_parquet_path raises ConfigurationError"""
    config = {"setup": {"census_parquet_path": ""}}

    with pytest.raises(ConfigurationError) as exc_info:
        SimulationService._validate_census(config, scenario_id="test_scenario", workspace_id="test_workspace")

    assert "census_parquet_path is required" in str(exc_info.value)

def test_validate_census_file_not_found():
    """Test that non-existent file raises ConfigurationError"""
    config = {"setup": {"census_parquet_path": "/nonexistent/path/census.parquet"}}

    with pytest.raises(ConfigurationError) as exc_info:
        SimulationService._validate_census(config, scenario_id="test_scenario", workspace_id="test_workspace")

    assert "Census file not found at" in str(exc_info.value)
    assert "/nonexistent/path/census.parquet" in str(exc_info.value)

def test_validate_census_valid_path(tmp_path):
    """Test that valid path with existing file passes validation"""
    census_file = tmp_path / "census.parquet"
    census_file.write_text("dummy parquet content")

    config = {"setup": {"census_parquet_path": str(census_file)}}

    # Should not raise
    SimulationService._validate_census(config, scenario_id="test_scenario", workspace_id="test_workspace")
```

**Fast Test Marker**:
```python
@pytest.mark.fast  # Runs in fast suite (<10s)
def test_validate_census_missing_key():
    ...
```

**Coverage**: Aim for 100% coverage of `_validate_census()` method.

---

## Error Message Examples

### Scenario 1: Missing Census Path

**User sees** (in Studio UI, Simulations tab, Run Status):
```
Configuration Error: census_parquet_path is required but was not found in the scenario config.
Ensure a census file has been uploaded to the scenario folder before running.
```

**In logs** (planalign_api server logs):
```
ERROR: execute_simulation failed
Exception: ConfigurationError
Message: census_parquet_path is required but was not found in the scenario config.
Ensure a census file has been uploaded to the scenario folder before running.

Execution Context:
  scenario_id: my-scenario-123
  workspace_id: workspace-456
  correlation_id: a1b2c3d4
  timestamp: 2026-03-18T14:23:45.123456Z
```

### Scenario 2: Census File Deleted

**User sees** (in Studio UI):
```
Configuration Error: Census file not found at '/workspaces/my-workspace/scenarios/my-scenario/data/census.parquet'.
Upload a valid census parquet file to the scenario folder and retry.
```

**In logs**:
```
ERROR: execute_simulation failed
Exception: ConfigurationError
Message: Census file not found at '/workspaces/my-workspace/scenarios/my-scenario/data/census.parquet'.
Upload a valid census parquet file to the scenario folder and retry.

Resolution Steps:
  1. Check the error message for the expected file path
  2. Verify the census.parquet file exists at that location
  3. If the file was moved or deleted, re-upload it via Studio
  4. If the path is incorrect, update it in scenario settings
  5. Retry the simulation
```

---

## Integration Points

### API Error Handler (No Changes Needed)

**Location**: `planalign_api/services/simulation/service.py:_handle_simulation_failure()`

**Current Flow**:
```python
except Exception as e:
    self._handle_simulation_failure(
        e, workspace_id, scenario_id, run_id,
        start_year, total_years, update_run_status,
    )
```

This already catches ConfigurationError and converts it to error message in UI. No changes needed.

### Studio Frontend Error Display (No Changes Needed)

**Current Contract**: Run status has `error_message` field that displays in UI.

ConfigurationError message will be displayed as-is in UI through existing error_message mechanism. No frontend changes needed.

---

## Dependencies

### Imports Needed

```python
# In planalign_api/services/simulation/service.py
from planalign_orchestrator.exceptions import ConfigurationError, ExecutionContext, ErrorSeverity
```

### Existing Classes Used

- `ConfigurationError` - Already exists in `planalign_orchestrator/exceptions.py`
- `ExecutionContext` - Already exists, used throughout codebase
- `ResolutionHint` - Already exists, used in error catalog
- `ErrorCatalog` - Already exists, patterns added to it

**No new dependencies added**. Feature uses existing infrastructure.

---

## Deployment Considerations

### Migration Notes

- **Breaking Change**: Simulations without census_parquet_path will now fail immediately instead of silently using a default
- **User Impact**: Users must upload a census file to any scenario before running a simulation
- **Remediation**: Upload census file via Studio UI (2-3 minutes per scenario)
- **Automated Fix**: None available (users must take action)

### Release Notes Entry

```markdown
### Breaking Change: Enforce Census Path Validation

Census path validation is now a hard requirement for running simulations. Simulations without a valid census file path configured and file present on disk will fail immediately with a clear error message.

**What changed:**
- Silent fallback to default census path has been removed
- Missing or invalid census paths now raise ConfigurationError immediately

**What you need to do:**
- Ensure all scenarios have a census.parquet file uploaded
- If you have existing scenarios, upload the census file via Studio before running simulations

**Error messages:**
- "census_parquet_path is required but was not found in the scenario config" → Upload a census file
- "Census file not found at '[path]'" → Verify the file exists at the expected location
```

---

## Testing Checklist

- [ ] Unit tests pass: `pytest tests/test_census_validation.py -m fast`
- [ ] Integration tests pass: `pytest tests/ -m integration`
- [ ] Coverage ≥90%: `pytest --cov=planalign_api.services.simulation tests/test_census_validation.py`
- [ ] Manual test: Create scenario, try to run without census → Error displayed in UI
- [ ] Manual test: Create scenario, upload census, run → Success
- [ ] Error catalog patterns match: ErrorCatalog finds hints for both error messages
- [ ] Logs include correlation_id and context
- [ ] Error message displays in Studio UI within 1 second of run attempt

---

## Code Review Checklist

- [ ] No silent fallback paths remain
- [ ] ConfigurationError used consistently (not ValueError)
- [ ] ExecutionContext populated with scenario_id
- [ ] Error messages match FR-002 and FR-004 exactly
- [ ] No new dependencies added
- [ ] Tests cover all edge cases (missing key, empty string, whitespace, missing file)
- [ ] Fast tests complete in <10s
- [ ] 90%+ coverage achieved
- [ ] Documentation updated (this quickstart, error messages)
