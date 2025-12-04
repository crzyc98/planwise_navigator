"""Production safety and orchestration settings.

E073: Config Module Refactoring - safety module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .paths import get_database_path
from .simulation import SimulationSettings, CompensationSettings
from .workforce import (
    WorkforceSettings,
    EnrollmentSettings,
    EligibilitySettings,
    PlanEligibilitySettings,
    EmployerMatchSettings,
)
from .performance import OptimizationSettings


class ProductionSafetySettings(BaseModel):
    """Production data safety and backup configuration."""

    # Database configuration
    db_path: str = Field(
        default_factory=lambda: str(get_database_path()),
        description="Path to simulation database"
    )

    # Backup configuration
    backup_enabled: bool = Field(default=True, description="Enable automatic backups")
    backup_dir: str = Field(default="backups", description="Backup directory path")
    backup_retention_days: int = Field(
        default=7, ge=1, description="Backup retention period"
    )
    backup_before_simulation: bool = Field(
        default=True, description="Create backup before each simulation"
    )

    # Verification settings
    verify_backups: bool = Field(default=True, description="Enable backup verification")
    max_backup_size_gb: float = Field(
        default=10.0, ge=0.1, description="Maximum backup size in GB"
    )

    # Logging configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_dir: str = Field(default="logs", description="Log directory path")

    # Safety checks
    require_backup_before_run: bool = Field(
        default=True, description="Require backup before simulation"
    )
    enable_emergency_backups: bool = Field(
        default=True, description="Create emergency backup on restore"
    )


class OrchestrationConfig(BaseModel):
    """Complete orchestration configuration including production safety."""

    model_config = ConfigDict(extra="allow")

    # Core simulation configuration
    simulation: SimulationSettings
    compensation: CompensationSettings
    workforce: WorkforceSettings = Field(default_factory=WorkforceSettings)
    enrollment: EnrollmentSettings = Field(default_factory=EnrollmentSettings)
    eligibility: EligibilitySettings = Field(default_factory=EligibilitySettings)
    plan_eligibility: PlanEligibilitySettings = Field(default_factory=PlanEligibilitySettings)
    employer_match: Optional[EmployerMatchSettings] = Field(default=None, description="Employer match configuration")

    # Performance optimization configuration
    optimization: OptimizationSettings = Field(default_factory=OptimizationSettings, description="Performance optimization settings")

    # Production safety configuration
    production_safety: ProductionSafetySettings = Field(default_factory=ProductionSafetySettings)

    # Enterprise identifiers
    scenario_id: Optional[str] = None
    plan_design_id: Optional[str] = None

    def require_identifiers(self) -> None:
        """Raise if scenario_id/plan_design_id are missing."""
        if not self.scenario_id or not self.plan_design_id:
            raise ValueError(
                "scenario_id and plan_design_id are required for orchestrator runs"
            )


def validate_production_configuration(config: OrchestrationConfig) -> None:
    """Validate production configuration for safety requirements.

    Story S043-02: Configuration Management

    Args:
        config: Complete orchestration configuration

    Raises:
        ValueError: If configuration validation fails
        FileNotFoundError: If required files don't exist
    """
    safety = config.production_safety

    # Validate database path exists
    db_path = Path(safety.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    # Validate database is accessible
    try:
        import duckdb

        with duckdb.connect(str(db_path)) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as e:
        raise ValueError(f"Database connection failed: {str(e)}")


def get_backup_configuration(config: OrchestrationConfig) -> dict:
    """Get backup configuration from orchestration config.

    Returns:
        Dictionary with backup settings
    """
    safety = config.production_safety
    return {
        "enabled": safety.backup_enabled,
        "backup_dir": safety.backup_dir,
        "retention_days": safety.backup_retention_days,
        "backup_before_simulation": safety.backup_before_simulation,
        "verify_backups": safety.verify_backups,
        "max_size_gb": safety.max_backup_size_gb,
    }
