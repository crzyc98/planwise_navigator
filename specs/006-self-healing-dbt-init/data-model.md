# Data Model: Self-Healing dbt Initialization

**Feature Branch**: `006-self-healing-dbt-init`
**Date**: 2025-12-12

## Entities

### InitializationState (Enum)

Represents the current state of database initialization.

```python
from enum import Enum

class InitializationState(str, Enum):
    """State machine for database initialization lifecycle."""
    NOT_STARTED = "not_started"      # No database or empty database
    IN_PROGRESS = "in_progress"      # Initialization currently running
    COMPLETED = "completed"          # All required tables exist and validated
    FAILED = "failed"                # Initialization failed, needs retry
```

**State Transitions**:
```
NOT_STARTED → IN_PROGRESS (on ensure_initialized())
IN_PROGRESS → COMPLETED (on successful validation)
IN_PROGRESS → FAILED (on error)
FAILED → IN_PROGRESS (on retry)
COMPLETED → NOT_STARTED (if tables manually dropped)
```

### RequiredTable (Pydantic Model)

Defines a table that must exist for simulations to run.

```python
from pydantic import BaseModel, Field
from enum import Enum
from typing import Literal

class TableTier(str, Enum):
    """Initialization tier determines build order."""
    SEED = "seed"           # Loaded via dbt seed
    FOUNDATION = "foundation"  # Built via dbt run

class RequiredTable(BaseModel):
    """Definition of a table required for simulation."""
    name: str = Field(..., description="Table name in database")
    tier: TableTier = Field(..., description="Initialization tier")
    dbt_selector: str = Field(..., description="dbt selector to build this table")

    class Config:
        frozen = True  # Immutable after creation
```

**Required Tables Registry**:
```python
REQUIRED_TABLES: list[RequiredTable] = [
    # Tier 1: Seeds (dbt seed)
    RequiredTable(name="config_age_bands", tier=TableTier.SEED, dbt_selector="config_age_bands"),
    RequiredTable(name="config_tenure_bands", tier=TableTier.SEED, dbt_selector="config_tenure_bands"),
    RequiredTable(name="config_job_levels", tier=TableTier.SEED, dbt_selector="config_job_levels"),
    RequiredTable(name="comp_levers", tier=TableTier.SEED, dbt_selector="comp_levers"),
    RequiredTable(name="irs_contribution_limits", tier=TableTier.SEED, dbt_selector="irs_contribution_limits"),

    # Tier 2: Foundation models (dbt run --select tag:foundation)
    RequiredTable(name="int_baseline_workforce", tier=TableTier.FOUNDATION, dbt_selector="int_baseline_workforce"),
    RequiredTable(name="int_employee_compensation_by_year", tier=TableTier.FOUNDATION, dbt_selector="int_employee_compensation_by_year"),
    RequiredTable(name="int_employee_benefits", tier=TableTier.FOUNDATION, dbt_selector="int_employee_benefits"),
]
```

### InitializationStep (Pydantic Model)

Represents a discrete step in the initialization process for progress tracking.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class InitializationStep(BaseModel):
    """A discrete step in the initialization process."""
    name: str = Field(..., description="Step identifier")
    display_name: str = Field(..., description="Human-readable step name")
    started_at: Optional[datetime] = Field(None, description="When step started")
    completed_at: Optional[datetime] = Field(None, description="When step completed")
    success: Optional[bool] = Field(None, description="Whether step succeeded")
    error_message: Optional[str] = Field(None, description="Error details if failed")

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate step duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def status(self) -> str:
        """Return step status string."""
        if self.completed_at is None and self.started_at is None:
            return "pending"
        elif self.completed_at is None:
            return "running"
        elif self.success:
            return "completed"
        else:
            return "failed"
```

**Standard Steps**:
```python
INITIALIZATION_STEPS = [
    InitializationStep(name="check_tables", display_name="Checking database tables"),
    InitializationStep(name="load_seeds", display_name="Loading seed data"),
    InitializationStep(name="build_foundation", display_name="Building foundation models"),
    InitializationStep(name="verify", display_name="Verifying initialization"),
]
```

### InitializationResult (Pydantic Model)

Complete result of an initialization attempt.

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class InitializationResult(BaseModel):
    """Result of a database initialization attempt."""
    state: InitializationState
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps: List[InitializationStep]
    missing_tables_found: List[str] = Field(default_factory=list)
    tables_created: List[str] = Field(default_factory=list)
    error: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def success(self) -> bool:
        return self.state == InitializationState.COMPLETED
```

## Relationships

```
InitializationResult
├── state: InitializationState (1:1)
├── steps: List[InitializationStep] (1:N)
└── missing_tables_found: List[str] (references RequiredTable.name)

RequiredTable
└── tier: TableTier (1:1)
```

## Validation Rules

### InitializationState Transitions

| From | To | Trigger | Validation |
|------|----|---------|------------|
| NOT_STARTED | IN_PROGRESS | `ensure_initialized()` called | Database path exists or can be created |
| IN_PROGRESS | COMPLETED | All tables verified | All `REQUIRED_TABLES` exist in database |
| IN_PROGRESS | FAILED | Error during init | Exception caught, error logged |
| FAILED | IN_PROGRESS | Retry requested | Database writable, mutex acquired |

### RequiredTable Validation

- `name`: Must be valid SQL identifier (alphanumeric + underscore)
- `tier`: Must be SEED or FOUNDATION
- `dbt_selector`: Must be valid dbt selector syntax

### InitializationStep Validation

- `started_at` must be set before `completed_at`
- `success` must be set when `completed_at` is set
- `error_message` should be set when `success` is False

## Database Schema Impact

This feature does **not** create new persistent tables. All entities above are runtime Python objects used for orchestration and progress tracking.

The feature ensures these **existing** tables are created:
- Seed tables in `dbt/seeds/` → loaded to `main` schema
- Foundation models in `dbt/models/intermediate/` → materialized to `main` schema

## Integration Points

### With Existing Code

| Component | Integration |
|-----------|-------------|
| `HookManager` | Register `AutoInitializer.ensure_initialized` as pre-simulation hook |
| `DatabaseConnectionManager` | Use for table existence checks |
| `DbtRunner` | Execute `dbt seed` and `dbt run` commands |
| `ExecutionMutex` | Prevent concurrent initialization attempts |
| `exceptions.py` | Add `InitializationError` exception class |

### With Logging (NFR-001/NFR-002)

Each `InitializationStep` completion logs:
```json
{
  "event": "initialization_step_complete",
  "step_name": "load_seeds",
  "started_at": "2025-12-12T10:00:00Z",
  "completed_at": "2025-12-12T10:00:15Z",
  "duration_seconds": 15.0,
  "success": true
}
```
