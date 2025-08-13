#!/usr/bin/env python3
"""
Pipeline Orchestration Engine

Coordinates config, dbt execution, registries, validation, and reporting for
multi-year simulations with basic checkpoint/restart support.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import SimulationConfig
from .config import to_dbt_vars
from .dbt_runner import DbtRunner, DbtResult
from .registries import RegistryManager
from .utils import DatabaseConnectionManager, ExecutionMutex, time_block
from .validation import DataValidator
from .reports import MultiYearReporter, YearAuditor, MultiYearSummary


class PipelineStageError(RuntimeError):
    pass


class WorkflowStage(Enum):
    INITIALIZATION = "initialization"
    FOUNDATION = "foundation"
    EVENT_GENERATION = "event_generation"
    STATE_ACCUMULATION = "state_accumulation"
    VALIDATION = "validation"
    REPORTING = "reporting"
    CLEANUP = "cleanup"


@dataclass
class StageDefinition:
    name: WorkflowStage
    dependencies: List[WorkflowStage]
    models: List[str]
    validation_rules: List[str]
    parallel_safe: bool = False
    checkpoint_enabled: bool = True


@dataclass
class WorkflowCheckpoint:
    year: int
    stage: WorkflowStage
    timestamp: str
    state_hash: str


class PipelineOrchestrator:
    def __init__(
        self,
        config: SimulationConfig,
        db_manager: DatabaseConnectionManager,
        dbt_runner: DbtRunner,
        registry_manager: RegistryManager,
        validator: DataValidator,
        *,
        reports_dir: Path | str = Path("reports"),
        checkpoints_dir: Path | str = Path(".navigator_checkpoints"),
        verbose: bool = False,
    ):
        self.config = config
        self.db_manager = db_manager
        self.dbt_runner = dbt_runner
        self.registry_manager = registry_manager
        self.validator = validator
        self.verbose = verbose
        self._dbt_vars = to_dbt_vars(config)
        # Debug (optional): show dbt vars derived from config
        if self.verbose:
            try:
                import json as _json
                print("\n🔎 Navigator Orchestrator dbt_vars (from config):")
                print(_json.dumps(self._dbt_vars, indent=2, sort_keys=True))
            except Exception:
                pass
        self.reports_dir = Path(reports_dir)
        self.checkpoints_dir = Path(checkpoints_dir)
        self.checkpoints_dir.mkdir(exist_ok=True)
        self._seeded = False

    def execute_multi_year_simulation(
        self,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        resume_from_checkpoint: bool = False,
        fail_on_validation_error: bool = False,
    ) -> MultiYearSummary:
        start = start_year or self.config.simulation.start_year
        end = end_year or self.config.simulation.end_year

        if resume_from_checkpoint:
            ckpt = self._find_last_checkpoint()
            if ckpt:
                start = max(start, ckpt.year)

        with ExecutionMutex("navigator_orchestrator"):
            # Optional one-time full reset before the yearly loop
            self._maybe_full_reset()
            completed_years: List[int] = []
            for year in range(start, end + 1):
                print(f"\n🔄 Starting simulation year {year}")
                self._execute_year_workflow(year, fail_on_validation_error=fail_on_validation_error)
                self._write_checkpoint(WorkflowCheckpoint(year, WorkflowStage.CLEANUP, datetime.utcnow().isoformat(), self._state_hash(year)))
                completed_years.append(year)

        # Final multi-year summary using reporter
        reporter = MultiYearReporter(self.db_manager)
        summary = reporter.generate_summary(completed_years)

        # Display comprehensive multi-year summary (matching monolithic script)
        reporter.display_comprehensive_multi_year_summary(completed_years)

        # Persist multi-year CSV summary
        out_csv = self.reports_dir / f"multi_year_summary_{completed_years[0]}_{completed_years[-1]}.csv"
        summary.export_csv(out_csv)
        return summary

    def _execute_year_workflow(self, year: int, *, fail_on_validation_error: bool) -> None:
        workflow = self._define_year_workflow(year)

        # Optional: clear existing rows for this year based on config.setup
        self._maybe_clear_year_data(year)

        # Ensure seeds are loaded once
        if not self._seeded:
            seed_res = self.dbt_runner.execute_command(["seed"], stream_output=True)
            if not seed_res.success:
                raise PipelineStageError(f"Dbt seed failed with code {seed_res.return_code}")
            self._seeded = True

        # Year 1 registry seeding
        if year == self.config.simulation.start_year:
            self.registry_manager.get_enrollment_registry().create_for_year(year)
            self.registry_manager.get_deferral_registry().create_table()

        for stage in workflow:
            print(f"   📋 Executing stage: {stage.name.value}")
            with time_block(f"stage:{stage.name.value}"):
                self._run_stage_models(stage, year)

            # Quick sanity: ensure workforce planning tables exist for this year
            if stage.name == WorkflowStage.FOUNDATION:
                def _chk(conn):
                    wn = conn.execute(
                        "SELECT COUNT(*) FROM int_workforce_needs WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    wnbl = conn.execute(
                        "SELECT COUNT(*) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    return int(wn), int(wnbl)
                wn_cnt, wnbl_cnt = self.db_manager.execute_with_retry(_chk)
                if wn_cnt == 0 or wnbl_cnt == 0:
                    print(
                        f"⚠️ workforce_needs rows={wn_cnt}, by_level rows={wnbl_cnt} for {year}. "
                        "Hiring may not meet growth targets."
                    )

            # Registry updates after events/state accumulation
            if stage.name == WorkflowStage.EVENT_GENERATION:
                self.registry_manager.get_enrollment_registry().update_post_year(year)
            if stage.name == WorkflowStage.STATE_ACCUMULATION:
                self.registry_manager.get_deferral_registry().update_post_year(year)

            # Stage-level validation hook
            if stage.name in (WorkflowStage.STATE_ACCUMULATION, WorkflowStage.VALIDATION):
                dv_results = self.validator.validate_year_results(year)
                if fail_on_validation_error and any((not r.passed and r.severity.value == "error") for r in dv_results):
                    raise PipelineStageError(f"Validation errors detected for year {year}")

        # Reporting per year
        auditor = YearAuditor(self.db_manager, self.validator)
        report = auditor.generate_report(year)
        report.export_json(self.reports_dir / f"year_{year}.json")

        # Display detailed year audit (matching monolithic script)
        auditor.generate_detailed_year_audit(year)

        self._verify_year_population(year)

    def _run_stage_models(self, stage: StageDefinition, year: int) -> None:
        if not stage.models:
            return
        if stage.parallel_safe and len(stage.models) > 1:
            results = self.dbt_runner.run_models(
                stage.models,
                parallel=True,
                simulation_year=year,
                dbt_vars=self._dbt_vars,
            )
            if not all(r.success for r in results):
                failed = [r for r in results if not r.success]
                raise PipelineStageError(f"Some models failed in stage {stage.name.value}: {[f.command for f in failed]}")
        else:
            # Run as a single selection for consistent dependency behavior
            selection = ["run", "--select", " ".join(stage.models)]
            res = self.dbt_runner.execute_command(
                selection,
                simulation_year=year,
                dbt_vars=self._dbt_vars,
                stream_output=True,
            )
            if not res.success:
                raise PipelineStageError(f"Dbt failed in stage {stage.name.value} with code {res.return_code}")

    def _maybe_clear_year_data(self, year: int) -> None:
        """Clear year-scoped data for idempotent re-runs when configured.

        Respects config.setup.clear_tables and config.setup.clear_table_patterns.
        Only deletes rows for the given simulation_year when the column exists.
        """
        setup = getattr(self.config, "setup", None)
        if not isinstance(setup, dict):
            return
        if not setup.get("clear_tables"):
            return
        # Respect clear_mode setting; skip year-level clears if full reset is requested
        clear_mode = setup.get("clear_mode", "all").lower()
        if clear_mode == "all":
            return
        patterns = setup.get("clear_table_patterns", ["int_", "fct_"])

        def _should_clear(name: str) -> bool:
            return any(name.startswith(p) for p in patterns)

        def _run(conn):
            tables = [r[0] for r in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
                """
            ).fetchall()]
            cleared = 0
            for t in tables:
                if not _should_clear(t):
                    continue
                # check if table has simulation_year column
                has_col = conn.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='main' AND table_name = ? AND column_name = 'simulation_year'
                    LIMIT 1
                    """,
                    [t],
                ).fetchone()
                if has_col:
                    conn.execute(f"DELETE FROM {t} WHERE simulation_year = ?", [year])
                    cleared += 1
            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared:
            print(f"🧹 Cleared year {year} rows in {cleared} table(s) per setup.clear_table_patterns")

    def _maybe_full_reset(self) -> None:
        """If configured, clear all rows from matching tables before yearly processing.

        Controlled by:
          setup.clear_tables: true/false
          setup.clear_mode: 'all' (default) or 'year'
          setup.clear_table_patterns: list of prefixes (default ['int_', 'fct_'])
        """
        setup = getattr(self.config, "setup", None)
        if not isinstance(setup, dict) or not setup.get("clear_tables"):
            return
        clear_mode = setup.get("clear_mode", "all").lower()
        if clear_mode != "all":
            return
        patterns = setup.get("clear_table_patterns", ["int_", "fct_"])

        def _should_clear(name: str) -> bool:
            return any(name.startswith(p) for p in patterns)

        def _run(conn):
            tables = [r[0] for r in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            ).fetchall()]
            cleared = 0
            for t in tables:
                if not _should_clear(t):
                    continue
                conn.execute(f"DELETE FROM {t}")
                cleared += 1
            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared:
            print(f"🧹 Full reset: cleared all rows in {cleared} table(s) per setup.clear_table_patterns")

    def _define_year_workflow(self, year: int) -> List[StageDefinition]:
        # For year 2+, need to include the previous year snapshot model to break circular dependencies
        initialization_models = ["stg_census_data"]
        if year > self.config.simulation.start_year:
            initialization_models.append("int_active_employees_prev_year_snapshot")

        return [
            StageDefinition(
                name=WorkflowStage.INITIALIZATION,
                dependencies=[],
                models=initialization_models,
                validation_rules=["data_freshness_check"],
            ),
            StageDefinition(
                name=WorkflowStage.FOUNDATION,
                dependencies=[WorkflowStage.INITIALIZATION],
                models=[
                    "int_baseline_workforce",
                    "int_employee_compensation_by_year",
                    "int_effective_parameters",
                    "int_workforce_needs",
                    "int_workforce_needs_by_level",
                ],
                validation_rules=["row_count_drift", "compensation_reasonableness"],
            ),
            StageDefinition(
                name=WorkflowStage.EVENT_GENERATION,
                dependencies=[WorkflowStage.FOUNDATION],
                models=[
                    "int_termination_events",
                    "int_hiring_events",
                    "int_new_hire_termination_events",
                    "int_hazard_promotion",
                    "int_hazard_merit",
                    "int_promotion_events",
                    "int_merit_events",
                    "int_eligibility_determination",
                    "int_enrollment_events",
                    # TODO: Fix deferral_escalation_registry table structure before re-enabling
                    # "int_deferral_rate_escalation_events",
                    # TODO: Check if match calculation models exist
                    # "int_employee_match_calculations",
                    # "fct_employer_match_events",
                ],
                validation_rules=["hire_termination_ratio", "event_sequence"],
                parallel_safe=False,  # Changed to false to ensure proper ordering
            ),
            StageDefinition(
                name=WorkflowStage.STATE_ACCUMULATION,
                dependencies=[WorkflowStage.EVENT_GENERATION],
                models=[
                    "fct_yearly_events",
                    "int_enrollment_state_accumulator",
                    "int_deferral_rate_state_accumulator",
                    "int_deferral_escalation_state_accumulator",
                    "int_employee_contributions",
                    "fct_workforce_snapshot",
                ],
                validation_rules=["state_consistency", "accumulator_integrity"],
                parallel_safe=False,  # Ensure proper sequencing of state models
            ),
            StageDefinition(
                name=WorkflowStage.VALIDATION,
                dependencies=[WorkflowStage.STATE_ACCUMULATION],
                models=[
                    "dq_employee_contributions_validation",
                ],
                validation_rules=["dq_suite"],
            ),
            StageDefinition(
                name=WorkflowStage.REPORTING,
                dependencies=[WorkflowStage.VALIDATION],
                models=[
                    # Future: Add reporting models here
                ],
                validation_rules=[],
            ),
        ]

    def _state_hash(self, year: int) -> str:
        # Lightweight placeholder hash combining year and timestamp
        return f"{year}:{datetime.utcnow().isoformat()}"

    def _verify_year_population(self, year: int) -> None:
        """Verify critical tables have rows for the given year; attempt one retry if empty."""
        def _counts(conn):
            snap = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            events = conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            return int(snap), int(events)

        snap_count, event_count = self.db_manager.execute_with_retry(_counts)
        if snap_count == 0 and event_count > 0:
            # Attempt targeted rebuild of snapshot once
            res = self.dbt_runner.execute_command(
                ["run", "--select", "fct_workforce_snapshot"],
                simulation_year=year,
                dbt_vars=self._dbt_vars,
                stream_output=True,
            )
            if not res.success:
                print(f"⚠️ Retry build of fct_workforce_snapshot failed for {year}")
            else:
                snap_count, _ = self.db_manager.execute_with_retry(_counts)
        if snap_count == 0:
            print(f"⚠️ fct_workforce_snapshot has 0 rows for {year}; verify upstream models and vars")

    def _write_checkpoint(self, ckpt: WorkflowCheckpoint) -> None:
        path = self.checkpoints_dir / f"year_{ckpt.year}.json"
        with open(path, "w") as fh:
            json.dump({
                "year": ckpt.year,
                "stage": ckpt.stage.value,
                "timestamp": ckpt.timestamp,
                "state_hash": ckpt.state_hash,
            }, fh)

    def _find_last_checkpoint(self) -> Optional[WorkflowCheckpoint]:
        files = sorted(self.checkpoints_dir.glob("year_*.json"))
        if not files:
            return None
        latest = files[-1]
        data = json.loads(latest.read_text())
        return WorkflowCheckpoint(
            year=int(data["year"]),
            stage=WorkflowStage(data["stage"]),
            timestamp=data["timestamp"],
            state_hash=data.get("state_hash", ""),
        )
