"""API-wide constants for Fidelity PlanAlign Engine."""

# Simulation telemetry constants
MAX_RECENT_EVENTS = 20  # Maximum number of recent events to show in telemetry

# Scenario comparison limits
MAX_SCENARIO_COMPARISON = 6  # Maximum scenarios for side-by-side comparison

# Default values for simulation results
DEFAULT_PARTICIPATION_RATE = 0.85  # Default plan participation rate when not calculated

# File types for artifact classification
ARTIFACT_TYPE_MAP = {
    ".xlsx": "excel",
    ".xls": "excel",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".duckdb": "duckdb",
    ".json": "json",
    ".txt": "text",
    ".csv": "text",
    ".log": "text",
}

# Media types for file downloads
MEDIA_TYPE_MAP = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".yaml": "application/x-yaml",
    ".yml": "application/x-yaml",
    ".json": "application/json",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".duckdb": "application/octet-stream",
}

# Run retention
DEFAULT_MAX_RUNS_PER_SCENARIO = 3  # Maximum runs to keep per scenario (0 = unlimited)
