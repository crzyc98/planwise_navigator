"""
from planalign_orchestrator.config import get_database_path
Unified Optimization Results Storage and Retrieval System for Fidelity PlanAlign Engine

This module provides a comprehensive storage system for optimization results from both
advanced_optimization.py and compensation_tuning.py interfaces, with integration to
DuckDB, versioning, metadata tracking, and export capabilities.

Features:
- Unified storage format for all optimization types
- DuckDB integration with existing simulation data
- Version control and metadata tracking
- Export capabilities (JSON, CSV, Excel)
- Caching strategies for performance
- Session state management integration
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import duckdb
import pandas as pd
import streamlit as st
import yaml
from pydantic import BaseModel, Field, validator

# Set up logging
logger = logging.getLogger(__name__)


class OptimizationType(str, Enum):
    """Types of optimization runs supported."""

    ADVANCED_SCIPY = "advanced_scipy"
    COMPENSATION_TUNING = "compensation_tuning"
    POLICY_OPTIMIZATION = "policy_optimization"
    MANUAL_ADJUSTMENT = "manual_adjustment"


class OptimizationStatus(str, Enum):
    """Status of optimization runs."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DRAFT = "draft"


class OptimizationEngine(str, Enum):
    """Optimization engines/algorithms used."""

    SCIPY_SLSQP = "scipy_slsqp"
    SCIPY_DE = "scipy_de"
    SCIPY_LBFGSB = "scipy_lbfgsb"
    MANUAL = "manual"
    GRID_SEARCH = "grid_search"
    GENETIC_ALGORITHM = "genetic_algorithm"


class ExportFormat(str, Enum):
    """Supported export formats."""

    JSON = "json"
    CSV = "csv"
    EXCEL = "excel"
    PARQUET = "parquet"
    PICKLE = "pickle"


@dataclass
class OptimizationObjective:
    """Single optimization objective configuration."""

    name: str
    weight: float
    target_value: Optional[float] = None
    direction: Literal["minimize", "maximize"] = "minimize"
    description: str = ""


@dataclass
class OptimizationConstraint:
    """Optimization constraint definition."""

    name: str
    constraint_type: Literal["equality", "inequality"]
    bounds: Optional[Tuple[float, float]] = None
    description: str = ""


class OptimizationMetadata(BaseModel):
    """Metadata for optimization runs."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    optimization_type: OptimizationType
    optimization_engine: OptimizationEngine
    status: OptimizationStatus
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Configuration
    random_seed: Optional[int] = None
    max_evaluations: Optional[int] = None
    timeout_minutes: Optional[int] = None
    use_synthetic_mode: bool = False

    # Runtime information
    runtime_seconds: Optional[float] = None
    function_evaluations: Optional[int] = None
    converged: Optional[bool] = None
    convergence_message: Optional[str] = None

    # Business context
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    business_justification: str = ""

    @validator("updated_at", always=True)
    def set_updated_at(cls, v):
        return datetime.now()


class OptimizationConfiguration(BaseModel):
    """Complete optimization configuration."""

    objectives: List[OptimizationObjective] = Field(default_factory=list)
    constraints: List[OptimizationConstraint] = Field(default_factory=list)
    initial_parameters: Dict[str, float] = Field(default_factory=dict)
    parameter_bounds: Dict[str, Tuple[float, float]] = Field(default_factory=dict)
    algorithm_config: Dict[str, Any] = Field(default_factory=dict)

    def calculate_hash(self) -> str:
        """Calculate configuration hash for deduplication."""
        config_str = json.dumps(self.dict(), sort_keys=True, default=str)
        return hashlib.md5(config_str.encode()).hexdigest()


class OptimizationResults(BaseModel):
    """Optimization results data."""

    objective_value: Optional[float] = None
    objective_breakdown: Dict[str, float] = Field(default_factory=dict)
    optimal_parameters: Dict[str, float] = Field(default_factory=dict)
    parameter_history: List[Dict[str, float]] = Field(default_factory=list)
    objective_history: List[float] = Field(default_factory=list)

    # Validation and risk assessment
    constraint_violations: List[str] = Field(default_factory=list)
    parameter_warnings: List[str] = Field(default_factory=list)
    risk_level: str = "MEDIUM"
    risk_assessment: Dict[str, Any] = Field(default_factory=dict)

    # Business impact
    estimated_cost_impact: Optional[Dict[str, Any]] = None
    estimated_employee_impact: Optional[Dict[str, Any]] = None
    projected_outcomes: Dict[str, Any] = Field(default_factory=dict)

    # Sensitivity analysis
    sensitivity_analysis: Dict[str, float] = Field(default_factory=dict)
    parameter_correlations: Dict[str, Dict[str, float]] = Field(default_factory=dict)


class OptimizationRun(BaseModel):
    """Complete optimization run record."""

    metadata: OptimizationMetadata
    configuration: OptimizationConfiguration
    results: OptimizationResults
    simulation_data: Optional[Dict[str, Any]] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }


class OptimizationStorage:
    """Unified storage manager for optimization results."""

    def __init__(self, db_path: str = str(get_database_path())):
        """Initialize the storage manager."""
        self.db_path = Path(db_path)
        self.cache = {}
        self.session_cache = {}
        self._init_storage()

    def _init_storage(self):
        """Initialize storage tables in DuckDB."""
        with duckdb.connect(str(self.db_path)) as conn:
            # Create optimization runs table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS optimization_runs (
                    run_id VARCHAR PRIMARY KEY,
                    scenario_id VARCHAR NOT NULL,
                    user_id VARCHAR,
                    session_id VARCHAR,
                    optimization_type VARCHAR NOT NULL,
                    optimization_engine VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    random_seed INTEGER,
                    max_evaluations INTEGER,
                    timeout_minutes INTEGER,
                    use_synthetic_mode BOOLEAN,
                    runtime_seconds DOUBLE,
                    function_evaluations INTEGER,
                    converged BOOLEAN,
                    convergence_message VARCHAR,
                    description VARCHAR,
                    tags VARCHAR,
                    business_justification VARCHAR,
                    configuration_hash VARCHAR
                )
            """
            )

            # Create optimization configurations table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS optimization_configurations (
                    configuration_hash VARCHAR PRIMARY KEY,
                    objectives VARCHAR NOT NULL,
                    constraints VARCHAR,
                    initial_parameters VARCHAR NOT NULL,
                    parameter_bounds VARCHAR,
                    algorithm_config VARCHAR,
                    created_at TIMESTAMP NOT NULL
                )
            """
            )

            # Create optimization results table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS optimization_results (
                    run_id VARCHAR PRIMARY KEY,
                    objective_value DOUBLE,
                    objective_breakdown VARCHAR,
                    optimal_parameters VARCHAR NOT NULL,
                    parameter_history VARCHAR,
                    objective_history VARCHAR,
                    constraint_violations VARCHAR,
                    parameter_warnings VARCHAR,
                    risk_level VARCHAR,
                    risk_assessment VARCHAR,
                    estimated_cost_impact VARCHAR,
                    estimated_employee_impact VARCHAR,
                    projected_outcomes VARCHAR,
                    sensitivity_analysis VARCHAR,
                    parameter_correlations VARCHAR
                )
            """
            )

            # Create optimization simulation data table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS optimization_simulation_data (
                    run_id VARCHAR PRIMARY KEY,
                    simulation_results VARCHAR,
                    workforce_snapshots VARCHAR,
                    event_data VARCHAR,
                    data_quality_metrics VARCHAR,
                    created_at TIMESTAMP NOT NULL
                )
            """
            )

            # Create optimization exports table for tracking exports
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS optimization_exports (
                    export_id VARCHAR PRIMARY KEY,
                    run_id VARCHAR NOT NULL,
                    export_format VARCHAR NOT NULL,
                    export_path VARCHAR NOT NULL,
                    exported_at TIMESTAMP NOT NULL,
                    exported_by VARCHAR,
                    file_size_bytes BIGINT
                )
            """
            )

            # Create indexes for better performance
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_optimization_runs_created_desc ON optimization_runs(created_at DESC)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_optimization_runs_scenario_status ON optimization_runs(scenario_id, status)"
                )
            except:
                pass  # Indexes might already exist

    def save_optimization_run(self, run: OptimizationRun) -> str:
        """Save a complete optimization run."""
        try:
            with duckdb.connect(str(self.db_path)) as conn:
                # Save configuration (if new)
                config_hash = run.configuration.calculate_hash()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO optimization_configurations
                    (configuration_hash, objectives, constraints, initial_parameters,
                     parameter_bounds, algorithm_config, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        config_hash,
                        json.dumps(
                            [asdict(obj) for obj in run.configuration.objectives]
                        ),
                        json.dumps(
                            [
                                asdict(constraint)
                                for constraint in run.configuration.constraints
                            ]
                        ),
                        json.dumps(run.configuration.initial_parameters),
                        json.dumps(run.configuration.parameter_bounds),
                        json.dumps(run.configuration.algorithm_config),
                        datetime.now(),
                    ],
                )

                # Save metadata
                metadata = run.metadata
                conn.execute(
                    """
                    INSERT OR REPLACE INTO optimization_runs
                    (run_id, scenario_id, user_id, session_id, optimization_type,
                     optimization_engine, status, created_at, updated_at, completed_at,
                     random_seed, max_evaluations, timeout_minutes, use_synthetic_mode,
                     runtime_seconds, function_evaluations, converged, convergence_message,
                     description, tags, business_justification, configuration_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        metadata.run_id,
                        metadata.scenario_id,
                        metadata.user_id,
                        metadata.session_id,
                        metadata.optimization_type.value,
                        metadata.optimization_engine.value,
                        metadata.status.value,
                        metadata.created_at,
                        metadata.updated_at,
                        metadata.completed_at,
                        metadata.random_seed,
                        metadata.max_evaluations,
                        metadata.timeout_minutes,
                        metadata.use_synthetic_mode,
                        metadata.runtime_seconds,
                        metadata.function_evaluations,
                        metadata.converged,
                        metadata.convergence_message,
                        metadata.description,
                        json.dumps(metadata.tags),
                        metadata.business_justification,
                        config_hash,
                    ],
                )

                # Save results
                results = run.results
                conn.execute(
                    """
                    INSERT OR REPLACE INTO optimization_results
                    (run_id, objective_value, objective_breakdown, optimal_parameters,
                     parameter_history, objective_history, constraint_violations, parameter_warnings,
                     risk_level, risk_assessment, estimated_cost_impact, estimated_employee_impact,
                     projected_outcomes, sensitivity_analysis, parameter_correlations)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        metadata.run_id,
                        results.objective_value,
                        json.dumps(results.objective_breakdown),
                        json.dumps(results.optimal_parameters),
                        json.dumps(results.parameter_history),
                        json.dumps(results.objective_history),
                        json.dumps(results.constraint_violations),
                        json.dumps(results.parameter_warnings),
                        results.risk_level,
                        json.dumps(results.risk_assessment),
                        json.dumps(results.estimated_cost_impact),
                        json.dumps(results.estimated_employee_impact),
                        json.dumps(results.projected_outcomes),
                        json.dumps(results.sensitivity_analysis),
                        json.dumps(results.parameter_correlations),
                    ],
                )

                # Save simulation data if present
                if run.simulation_data:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO optimization_simulation_data
                        (run_id, simulation_results, workforce_snapshots, event_data,
                         data_quality_metrics, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        [
                            metadata.run_id,
                            json.dumps(
                                run.simulation_data.get("simulation_results", {})
                            ),
                            json.dumps(
                                run.simulation_data.get("workforce_snapshots", {})
                            ),
                            json.dumps(run.simulation_data.get("event_data", {})),
                            json.dumps(
                                run.simulation_data.get("data_quality_metrics", {})
                            ),
                            datetime.now(),
                        ],
                    )

            # Update cache
            self.cache[metadata.run_id] = run
            logger.info(f"Saved optimization run {metadata.run_id}")
            return metadata.run_id

        except Exception as e:
            logger.error(f"Failed to save optimization run: {e}")
            raise

    def load_optimization_run(self, run_id: str) -> Optional[OptimizationRun]:
        """Load a complete optimization run by ID."""
        # Check cache first
        if run_id in self.cache:
            return self.cache[run_id]

        try:
            with duckdb.connect(str(self.db_path)) as conn:
                # Load metadata
                metadata_row = conn.execute(
                    """
                    SELECT * FROM optimization_runs WHERE run_id = ?
                """,
                    [run_id],
                ).fetchone()

                if not metadata_row:
                    return None

                # Load configuration
                config_row = conn.execute(
                    """
                    SELECT * FROM optimization_configurations
                    WHERE configuration_hash = ?
                """,
                    [metadata_row[21]],
                ).fetchone()  # configuration_hash column

                # Load results
                results_row = conn.execute(
                    """
                    SELECT * FROM optimization_results WHERE run_id = ?
                """,
                    [run_id],
                ).fetchone()

                # Load simulation data
                sim_data_row = conn.execute(
                    """
                    SELECT * FROM optimization_simulation_data WHERE run_id = ?
                """,
                    [run_id],
                ).fetchone()

                # Reconstruct objects
                run = self._reconstruct_optimization_run(
                    metadata_row, config_row, results_row, sim_data_row
                )

                # Cache the result
                if run:
                    self.cache[run_id] = run

                return run

        except Exception as e:
            logger.error(f"Failed to load optimization run {run_id}: {e}")
            return None

    def _reconstruct_optimization_run(
        self, metadata_row, config_row, results_row, sim_data_row
    ) -> OptimizationRun:
        """Reconstruct OptimizationRun from database rows."""
        # Reconstruct metadata
        metadata = OptimizationMetadata(
            run_id=metadata_row[0],
            scenario_id=metadata_row[1],
            user_id=metadata_row[2],
            session_id=metadata_row[3],
            optimization_type=OptimizationType(metadata_row[4]),
            optimization_engine=OptimizationEngine(metadata_row[5]),
            status=OptimizationStatus(metadata_row[6]),
            created_at=metadata_row[7],
            updated_at=metadata_row[8],
            completed_at=metadata_row[9],
            random_seed=metadata_row[10],
            max_evaluations=metadata_row[11],
            timeout_minutes=metadata_row[12],
            use_synthetic_mode=metadata_row[13],
            runtime_seconds=metadata_row[14],
            function_evaluations=metadata_row[15],
            converged=metadata_row[16],
            convergence_message=metadata_row[17],
            description=metadata_row[18],
            tags=json.loads(metadata_row[19]) if metadata_row[19] else [],
            business_justification=metadata_row[20],
        )

        # Reconstruct configuration
        if config_row:
            objectives_data = json.loads(config_row[1])
            objectives = [OptimizationObjective(**obj) for obj in objectives_data]

            constraints_data = json.loads(config_row[2]) if config_row[2] else []
            constraints = [
                OptimizationConstraint(**const) for const in constraints_data
            ]

            configuration = OptimizationConfiguration(
                objectives=objectives,
                constraints=constraints,
                initial_parameters=json.loads(config_row[3]),
                parameter_bounds=json.loads(config_row[4]) if config_row[4] else {},
                algorithm_config=json.loads(config_row[5]) if config_row[5] else {},
            )
        else:
            configuration = OptimizationConfiguration()

        # Reconstruct results
        if results_row:
            results = OptimizationResults(
                objective_value=results_row[1],
                objective_breakdown=json.loads(results_row[2])
                if results_row[2]
                else {},
                optimal_parameters=json.loads(results_row[3]),
                parameter_history=json.loads(results_row[4]) if results_row[4] else [],
                objective_history=json.loads(results_row[5]) if results_row[5] else [],
                constraint_violations=json.loads(results_row[6])
                if results_row[6]
                else [],
                parameter_warnings=json.loads(results_row[7]) if results_row[7] else [],
                risk_level=results_row[8] or "MEDIUM",
                risk_assessment=json.loads(results_row[9]) if results_row[9] else {},
                estimated_cost_impact=json.loads(results_row[10])
                if results_row[10]
                else None,
                estimated_employee_impact=json.loads(results_row[11])
                if results_row[11]
                else None,
                projected_outcomes=json.loads(results_row[12])
                if results_row[12]
                else {},
                sensitivity_analysis=json.loads(results_row[13])
                if results_row[13]
                else {},
                parameter_correlations=json.loads(results_row[14])
                if results_row[14]
                else {},
            )
        else:
            results = OptimizationResults()

        # Reconstruct simulation data
        simulation_data = None
        if sim_data_row:
            simulation_data = {
                "simulation_results": json.loads(sim_data_row[1])
                if sim_data_row[1]
                else {},
                "workforce_snapshots": json.loads(sim_data_row[2])
                if sim_data_row[2]
                else {},
                "event_data": json.loads(sim_data_row[3]) if sim_data_row[3] else {},
                "data_quality_metrics": json.loads(sim_data_row[4])
                if sim_data_row[4]
                else {},
            }

        return OptimizationRun(
            metadata=metadata,
            configuration=configuration,
            results=results,
            simulation_data=simulation_data,
        )

    def list_optimization_runs(
        self,
        scenario_id: Optional[str] = None,
        optimization_type: Optional[OptimizationType] = None,
        status: Optional[OptimizationStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[OptimizationMetadata]:
        """List optimization runs with optional filters."""
        try:
            with duckdb.connect(str(self.db_path)) as conn:
                query = "SELECT * FROM optimization_runs"
                params = []
                conditions = []

                if scenario_id:
                    conditions.append("scenario_id = ?")
                    params.append(scenario_id)

                if optimization_type:
                    conditions.append("optimization_type = ?")
                    params.append(optimization_type.value)

                if status:
                    conditions.append("status = ?")
                    params.append(status.value)

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                rows = conn.execute(query, params).fetchall()

                results = []
                for row in rows:
                    metadata = OptimizationMetadata(
                        run_id=row[0],
                        scenario_id=row[1],
                        user_id=row[2],
                        session_id=row[3],
                        optimization_type=OptimizationType(row[4]),
                        optimization_engine=OptimizationEngine(row[5]),
                        status=OptimizationStatus(row[6]),
                        created_at=row[7],
                        updated_at=row[8],
                        completed_at=row[9],
                        random_seed=row[10],
                        max_evaluations=row[11],
                        timeout_minutes=row[12],
                        use_synthetic_mode=row[13],
                        runtime_seconds=row[14],
                        function_evaluations=row[15],
                        converged=row[16],
                        convergence_message=row[17],
                        description=row[18],
                        tags=json.loads(row[19]) if row[19] else [],
                        business_justification=row[20],
                    )
                    results.append(metadata)

                return results

        except Exception as e:
            logger.error(f"Failed to list optimization runs: {e}")
            return []

    def delete_optimization_run(self, run_id: str) -> bool:
        """Delete an optimization run and all related data."""
        try:
            with duckdb.connect(str(self.db_path)) as conn:
                # Delete in reverse dependency order
                conn.execute(
                    "DELETE FROM optimization_exports WHERE run_id = ?", [run_id]
                )
                conn.execute(
                    "DELETE FROM optimization_simulation_data WHERE run_id = ?",
                    [run_id],
                )
                conn.execute(
                    "DELETE FROM optimization_results WHERE run_id = ?", [run_id]
                )
                conn.execute("DELETE FROM optimization_runs WHERE run_id = ?", [run_id])

            # Remove from cache
            if run_id in self.cache:
                del self.cache[run_id]

            logger.info(f"Deleted optimization run {run_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete optimization run {run_id}: {e}")
            return False

    def export_optimization_run(
        self,
        run_id: str,
        format: ExportFormat,
        output_path: Optional[str] = None,
        include_simulation_data: bool = True,
    ) -> str:
        """Export an optimization run to specified format."""
        run = self.load_optimization_run(run_id)
        if not run:
            raise ValueError(f"Optimization run {run_id} not found")

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"optimization_export_{run_id}_{timestamp}.{format.value}"

        output_path = Path(output_path)

        try:
            if format == ExportFormat.JSON:
                with open(output_path, "w") as f:
                    json.dump(run.dict(), f, indent=2, default=str)

            elif format == ExportFormat.PICKLE:
                with open(output_path, "wb") as f:
                    pickle.dump(run, f)

            elif format == ExportFormat.CSV:
                # Export as multiple CSV files in a directory
                export_dir = output_path.with_suffix("")
                export_dir.mkdir(exist_ok=True)

                # Metadata CSV
                metadata_df = pd.DataFrame([run.metadata.dict()])
                metadata_df.to_csv(export_dir / "metadata.csv", index=False)

                # Parameters CSV
                params_df = pd.DataFrame([run.results.optimal_parameters])
                params_df.to_csv(export_dir / "optimal_parameters.csv", index=False)

                # Parameter history CSV
                if run.results.parameter_history:
                    history_df = pd.DataFrame(run.results.parameter_history)
                    history_df.to_csv(export_dir / "parameter_history.csv", index=False)

                # Objectives CSV
                objectives_df = pd.DataFrame([run.results.objective_breakdown])
                objectives_df.to_csv(
                    export_dir / "objective_breakdown.csv", index=False
                )

            elif format == ExportFormat.EXCEL:
                with pd.ExcelWriter(output_path) as writer:
                    # Metadata sheet
                    metadata_df = pd.DataFrame([run.metadata.dict()])
                    metadata_df.to_excel(writer, sheet_name="Metadata", index=False)

                    # Parameters sheet
                    params_df = pd.DataFrame([run.results.optimal_parameters])
                    params_df.to_excel(
                        writer, sheet_name="Optimal_Parameters", index=False
                    )

                    # Parameter history sheet
                    if run.results.parameter_history:
                        history_df = pd.DataFrame(run.results.parameter_history)
                        history_df.to_excel(
                            writer, sheet_name="Parameter_History", index=False
                        )

                    # Objectives sheet
                    objectives_df = pd.DataFrame([run.results.objective_breakdown])
                    objectives_df.to_excel(
                        writer, sheet_name="Objective_Breakdown", index=False
                    )

                    # Risk assessment sheet
                    if run.results.risk_assessment:
                        risk_df = pd.DataFrame([run.results.risk_assessment])
                        risk_df.to_excel(
                            writer, sheet_name="Risk_Assessment", index=False
                        )

            elif format == ExportFormat.PARQUET:
                # Convert to DataFrame and save as parquet
                export_data = {
                    "run_id": [run.metadata.run_id],
                    "scenario_id": [run.metadata.scenario_id],
                    "optimization_type": [run.metadata.optimization_type.value],
                    "status": [run.metadata.status.value],
                    "created_at": [run.metadata.created_at],
                    "objective_value": [run.results.objective_value],
                    "optimal_parameters": [json.dumps(run.results.optimal_parameters)],
                    "risk_level": [run.results.risk_level],
                }
                df = pd.DataFrame(export_data)
                df.to_parquet(output_path, index=False)

            # Record the export
            self._record_export(run_id, format, str(output_path))

            logger.info(f"Exported optimization run {run_id} to {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Failed to export optimization run {run_id}: {e}")
            raise

    def _record_export(self, run_id: str, format: ExportFormat, export_path: str):
        """Record an export in the database."""
        try:
            export_id = str(uuid.uuid4())
            file_size = (
                Path(export_path).stat().st_size if Path(export_path).exists() else 0
            )

            with duckdb.connect(str(self.db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO optimization_exports
                    (export_id, run_id, export_format, export_path, exported_at, file_size_bytes)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    [
                        export_id,
                        run_id,
                        format.value,
                        export_path,
                        datetime.now(),
                        file_size,
                    ],
                )

        except Exception as e:
            logger.warning(f"Failed to record export: {e}")

    def get_export_history(self, run_id: str) -> List[Dict[str, Any]]:
        """Get export history for a run."""
        try:
            with duckdb.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    """
                    SELECT export_id, export_format, export_path, exported_at, file_size_bytes
                    FROM optimization_exports
                    WHERE run_id = ?
                    ORDER BY exported_at DESC
                """,
                    [run_id],
                ).fetchall()

                return [
                    {
                        "export_id": row[0],
                        "format": row[1],
                        "path": row[2],
                        "exported_at": row[3],
                        "file_size_bytes": row[4],
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"Failed to get export history for {run_id}: {e}")
            return []

    def search_optimization_runs(
        self, query: str, search_fields: List[str] = None
    ) -> List[OptimizationMetadata]:
        """Search optimization runs by text query."""
        if search_fields is None:
            search_fields = ["scenario_id", "description", "business_justification"]

        try:
            with duckdb.connect(str(self.db_path)) as conn:
                conditions = []
                params = []

                for field in search_fields:
                    conditions.append(f"{field} LIKE ?")
                    params.append(f"%{query}%")

                sql_query = f"""
                    SELECT * FROM optimization_runs
                    WHERE {' OR '.join(conditions)}
                    ORDER BY created_at DESC
                    LIMIT 50
                """

                rows = conn.execute(sql_query, params).fetchall()

                results = []
                for row in rows:
                    metadata = OptimizationMetadata(
                        run_id=row[0],
                        scenario_id=row[1],
                        user_id=row[2],
                        session_id=row[3],
                        optimization_type=OptimizationType(row[4]),
                        optimization_engine=OptimizationEngine(row[5]),
                        status=OptimizationStatus(row[6]),
                        created_at=row[7],
                        updated_at=row[8],
                        completed_at=row[9],
                        random_seed=row[10],
                        max_evaluations=row[11],
                        timeout_minutes=row[12],
                        use_synthetic_mode=row[13],
                        runtime_seconds=row[14],
                        function_evaluations=row[15],
                        converged=row[16],
                        convergence_message=row[17],
                        description=row[18],
                        tags=json.loads(row[19]) if row[19] else [],
                        business_justification=row[20],
                    )
                    results.append(metadata)

                return results

        except Exception as e:
            logger.error(f"Failed to search optimization runs: {e}")
            return []


class OptimizationStorageManager:
    """High-level manager for optimization storage with caching and session integration."""

    def __init__(self, db_path: str = str(get_database_path())):
        """Initialize the storage manager."""
        self.storage = OptimizationStorage(db_path)
        self.session_key = "optimization_storage_cache"

    def init_session_state(self):
        """Initialize Streamlit session state for optimization storage."""
        if self.session_key not in st.session_state:
            st.session_state[self.session_key] = {
                "recent_runs": [],
                "current_run_id": None,
                "cached_results": {},
                "last_refresh": datetime.now(),
            }

    def save_run_with_session_cache(self, run: OptimizationRun) -> str:
        """Save run and update session cache."""
        run_id = self.storage.save_optimization_run(run)

        # Update session state if available
        if "st" in globals() and hasattr(st, "session_state"):
            self.init_session_state()
            cache = st.session_state[self.session_key]
            cache["current_run_id"] = run_id
            cache["cached_results"][run_id] = run
            cache["last_refresh"] = datetime.now()

            # Add to recent runs
            if run_id not in [r.run_id for r in cache["recent_runs"]]:
                cache["recent_runs"].insert(0, run.metadata)
                cache["recent_runs"] = cache["recent_runs"][
                    :10
                ]  # Keep only 10 most recent

        return run_id

    def load_run_with_session_cache(self, run_id: str) -> Optional[OptimizationRun]:
        """Load run with session caching."""
        # Check session cache first
        if "st" in globals() and hasattr(st, "session_state"):
            self.init_session_state()
            cache = st.session_state[self.session_key]
            if run_id in cache["cached_results"]:
                return cache["cached_results"][run_id]

        # Load from storage
        run = self.storage.load_optimization_run(run_id)

        # Cache in session if available
        if run and "st" in globals() and hasattr(st, "session_state"):
            cache = st.session_state[self.session_key]
            cache["cached_results"][run_id] = run

        return run

    def get_recent_runs(self, limit: int = 10) -> List[OptimizationMetadata]:
        """Get recent optimization runs."""
        # Try session cache first
        if "st" in globals() and hasattr(st, "session_state"):
            self.init_session_state()
            cache = st.session_state[self.session_key]
            if cache["recent_runs"] and len(cache["recent_runs"]) >= limit:
                return cache["recent_runs"][:limit]

        # Load from storage
        recent_runs = self.storage.list_optimization_runs(limit=limit)

        # Update session cache
        if "st" in globals() and hasattr(st, "session_state"):
            cache = st.session_state[self.session_key]
            cache["recent_runs"] = recent_runs
            cache["last_refresh"] = datetime.now()

        return recent_runs

    def clear_session_cache(self):
        """Clear session cache."""
        if "st" in globals() and hasattr(st, "session_state"):
            if self.session_key in st.session_state:
                st.session_state[self.session_key] = {
                    "recent_runs": [],
                    "current_run_id": None,
                    "cached_results": {},
                    "last_refresh": datetime.now(),
                }


# Singleton instance for the application
_storage_manager = None


def get_optimization_storage() -> OptimizationStorageManager:
    """Get the singleton optimization storage manager."""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = OptimizationStorageManager()
    return _storage_manager


# Convenience functions for legacy compatibility
def save_optimization_result(
    scenario_id: str,
    optimization_type: str,
    results: Dict[str, Any],
    configuration: Dict[str, Any] = None,
    metadata: Dict[str, Any] = None,
) -> str:
    """Legacy function to save optimization results."""
    storage = get_optimization_storage()

    # Convert legacy format to new format
    opt_metadata = OptimizationMetadata(
        scenario_id=scenario_id,
        optimization_type=OptimizationType(optimization_type),
        optimization_engine=OptimizationEngine.MANUAL,
        status=OptimizationStatus.COMPLETED,
        **(metadata or {}),
    )

    opt_config = OptimizationConfiguration(**(configuration or {}))
    opt_results = OptimizationResults(**(results or {}))

    run = OptimizationRun(
        metadata=opt_metadata, configuration=opt_config, results=opt_results
    )

    return storage.save_run_with_session_cache(run)


def load_optimization_result(run_id: str) -> Optional[Dict[str, Any]]:
    """Legacy function to load optimization results."""
    storage = get_optimization_storage()
    run = storage.load_run_with_session_cache(run_id)
    return run.dict() if run else None


def get_recent_optimization_results(limit: int = 10) -> List[Dict[str, Any]]:
    """Legacy function to get recent optimization results."""
    storage = get_optimization_storage()
    recent_runs = storage.get_recent_runs(limit)
    return [metadata.dict() for metadata in recent_runs]


if __name__ == "__main__":
    # Example usage and testing
    storage = OptimizationStorageManager()

    # Create a sample optimization run
    metadata = OptimizationMetadata(
        scenario_id="test_scenario_001",
        optimization_type=OptimizationType.ADVANCED_SCIPY,
        optimization_engine=OptimizationEngine.SCIPY_SLSQP,
        status=OptimizationStatus.COMPLETED,
        description="Test optimization run",
        random_seed=42,
        max_evaluations=100,
        runtime_seconds=45.2,
        function_evaluations=87,
        converged=True,
    )

    configuration = OptimizationConfiguration(
        objectives=[
            OptimizationObjective(name="cost", weight=0.4, direction="minimize"),
            OptimizationObjective(name="equity", weight=0.3, direction="minimize"),
            OptimizationObjective(name="targets", weight=0.3, direction="minimize"),
        ],
        initial_parameters={
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "cola_rate": 0.025,
        },
    )

    results = OptimizationResults(
        objective_value=0.234567,
        optimal_parameters={
            "merit_rate_level_1": 0.042,
            "merit_rate_level_2": 0.038,
            "cola_rate": 0.023,
        },
        risk_level="MEDIUM",
    )

    run = OptimizationRun(
        metadata=metadata, configuration=configuration, results=results
    )

    # Save the run
    run_id = storage.save_run_with_session_cache(run)
    print(f"Saved optimization run: {run_id}")

    # Load the run
    loaded_run = storage.load_run_with_session_cache(run_id)
    if loaded_run:
        print(f"Loaded run: {loaded_run.metadata.scenario_id}")
        print(f"Objective value: {loaded_run.results.objective_value}")

    # Export the run
    export_path = storage.storage.export_optimization_run(run_id, ExportFormat.JSON)
    print(f"Exported to: {export_path}")

    # List recent runs
    recent = storage.get_recent_runs(5)
    print(f"Found {len(recent)} recent runs")
