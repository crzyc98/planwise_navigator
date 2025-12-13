"""
Initialization State and Data Models for Self-Healing dbt Initialization.

Provides Pydantic models for tracking database initialization state,
required tables, and initialization progress. These models enable
type-safe configuration and structured logging of the initialization
process.

Models:
- InitializationState: Enum for initialization lifecycle states
- TableTier: Enum for table initialization order (SEED vs FOUNDATION)
- RequiredTable: Definition of a table required for simulation
- InitializationStep: A discrete step in the initialization process
- InitializationResult: Complete result of an initialization attempt

Constants:
- REQUIRED_TABLES: Registry of all tables required for simulation
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class InitializationState(str, Enum):
    """State machine for database initialization lifecycle.

    States:
        NOT_STARTED: No database or empty database, initialization needed
        IN_PROGRESS: Initialization currently running
        COMPLETED: All required tables exist and validated
        FAILED: Initialization failed, needs retry

    State Transitions:
        NOT_STARTED → IN_PROGRESS (on ensure_initialized())
        IN_PROGRESS → COMPLETED (on successful validation)
        IN_PROGRESS → FAILED (on error)
        FAILED → IN_PROGRESS (on retry)
        COMPLETED → NOT_STARTED (if tables manually dropped)
    """
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TableTier(str, Enum):
    """Initialization tier determines build order.

    Tiers:
        SEED: Tables loaded via `dbt seed` command (configuration data)
        FOUNDATION: Tables built via `dbt run` after seeds are loaded

    Build Order:
        1. All SEED tier tables are loaded first
        2. All FOUNDATION tier tables are built after seeds complete
    """
    SEED = "seed"
    FOUNDATION = "foundation"


class RequiredTable(BaseModel):
    """Definition of a table required for simulation.

    Attributes:
        name: Table name in database (must be valid SQL identifier)
        tier: Initialization tier (SEED or FOUNDATION)
        dbt_selector: dbt selector to build this table

    Example:
        >>> table = RequiredTable(
        ...     name="config_age_bands",
        ...     tier=TableTier.SEED,
        ...     dbt_selector="config_age_bands"
        ... )
    """
    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Table name in database")
    tier: TableTier = Field(..., description="Initialization tier")
    dbt_selector: str = Field(..., description="dbt selector to build this table")


# Registry of all required tables for simulation
# Per spec clarification: Seed tables + foundation models
REQUIRED_TABLES: List[RequiredTable] = [
    # Tier 1: Seeds (dbt seed)
    RequiredTable(
        name="config_age_bands",
        tier=TableTier.SEED,
        dbt_selector="config_age_bands"
    ),
    RequiredTable(
        name="config_tenure_bands",
        tier=TableTier.SEED,
        dbt_selector="config_tenure_bands"
    ),
    RequiredTable(
        name="config_job_levels",
        tier=TableTier.SEED,
        dbt_selector="config_job_levels"
    ),
    RequiredTable(
        name="comp_levers",
        tier=TableTier.SEED,
        dbt_selector="comp_levers"
    ),
    RequiredTable(
        name="irs_contribution_limits",
        tier=TableTier.SEED,
        dbt_selector="irs_contribution_limits"
    ),
    # Tier 2: Foundation models (dbt run --select tag:FOUNDATION)
    # These models already have tags=['FOUNDATION'] in their config
    RequiredTable(
        name="int_baseline_workforce",
        tier=TableTier.FOUNDATION,
        dbt_selector="int_baseline_workforce"
    ),
    RequiredTable(
        name="int_employee_compensation_by_year",
        tier=TableTier.FOUNDATION,
        dbt_selector="int_employee_compensation_by_year"
    ),
]


class InitializationStep(BaseModel):
    """A discrete step in the initialization process for progress tracking.

    Attributes:
        name: Step identifier (used in logs and error messages)
        display_name: Human-readable step name (shown in progress output)
        started_at: When step started (None if not started)
        completed_at: When step completed (None if not completed)
        success: Whether step succeeded (None if not completed)
        error_message: Error details if failed (None if succeeded)

    Properties:
        duration_seconds: Step duration in seconds (None if not completed)
        status: Current step status string ("pending", "running", "completed", "failed")

    Example:
        >>> step = InitializationStep(
        ...     name="load_seeds",
        ...     display_name="Loading seed data"
        ... )
        >>> step.status
        'pending'
    """
    model_config = ConfigDict(validate_assignment=True)

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


def create_standard_steps() -> List[InitializationStep]:
    """Create the standard initialization steps.

    Returns a fresh list of InitializationStep objects for a new
    initialization attempt. Each step is in 'pending' status.

    Returns:
        List of standard initialization steps in execution order

    Steps:
        1. check_tables: Checking database tables
        2. load_seeds: Loading seed data
        3. build_foundation: Building foundation models
        4. verify: Verifying initialization
    """
    return [
        InitializationStep(
            name="check_tables",
            display_name="Checking database tables"
        ),
        InitializationStep(
            name="load_seeds",
            display_name="Loading seed data"
        ),
        InitializationStep(
            name="build_foundation",
            display_name="Building foundation models"
        ),
        InitializationStep(
            name="verify",
            display_name="Verifying initialization"
        ),
    ]


class InitializationResult(BaseModel):
    """Complete result of a database initialization attempt.

    Attributes:
        state: Final initialization state
        started_at: When initialization started
        completed_at: When initialization completed (None if still running)
        steps: List of initialization steps with timing/status
        missing_tables_found: Tables that were missing at start
        tables_created: Tables that were created during initialization
        error: Error message if initialization failed

    Properties:
        duration_seconds: Total duration in seconds (None if not completed)
        success: True if state is COMPLETED

    Example:
        >>> result = InitializationResult(
        ...     state=InitializationState.COMPLETED,
        ...     started_at=datetime.now(),
        ...     steps=create_standard_steps()
        ... )
        >>> result.success
        True
    """
    state: InitializationState
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps: List[InitializationStep] = Field(default_factory=list)
    missing_tables_found: List[str] = Field(default_factory=list)
    tables_created: List[str] = Field(default_factory=list)
    error: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate total initialization duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def success(self) -> bool:
        """Return True if initialization completed successfully."""
        return self.state == InitializationState.COMPLETED
