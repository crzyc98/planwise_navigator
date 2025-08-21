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
from navigator_orchestrator.config import get_database_path
from pathlib import Path
from typing import Any, Dict, List, Optional

from .checkpoint_manager import CheckpointManager
from .config import SimulationConfig, to_dbt_vars
from .dbt_runner import DbtResult, DbtRunner
from .recovery_orchestrator import RecoveryOrchestrator
from .registries import RegistryManager
from .reports import MultiYearReporter, MultiYearSummary, YearAuditor
from .utils import DatabaseConnectionManager, ExecutionMutex, time_block
from .validation import DataValidator


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
        enhanced_checkpoints: bool = True,
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

        # Enhanced checkpoint system
        self.enhanced_checkpoints = enhanced_checkpoints
        if enhanced_checkpoints:
            # Determine database path from db_manager
            db_path = getattr(db_manager, "db_path", str(get_database_path()))
            self.checkpoint_manager = CheckpointManager(
                checkpoint_dir=str(checkpoints_dir), db_path=str(db_path)
            )
            self.recovery_orchestrator = RecoveryOrchestrator(self.checkpoint_manager)
            self.config_hash = self._calculate_config_hash()
        else:
            self.checkpoint_manager = None
            self.recovery_orchestrator = None
            self.config_hash = None

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
            # Ensure orchestrator-managed registries start clean for a new run
            # These tables are not year-partitioned; stale state can block auto-enrollment
            if not resume_from_checkpoint:
                try:
                    er = self.registry_manager.get_enrollment_registry()
                    dr = self.registry_manager.get_deferral_registry()
                    er.create_table()
                    dr.create_table()
                    # Reset only when starting at configured first year (fresh simulation)
                    if start == self.config.simulation.start_year:
                        er.reset()
                        dr.reset()
                        if self.verbose:
                            print(
                                "🧹 Cleared enrollment/deferral registries for fresh run"
                            )
                except Exception:
                    # Non-fatal; proceed even if reset fails
                    pass
            completed_years: List[int] = []
            for year in range(start, end + 1):
                print(f"\n🔄 Starting simulation year {year}")
                self._execute_year_workflow(
                    year, fail_on_validation_error=fail_on_validation_error
                )

                # Create checkpoint using enhanced system if available
                if (
                    self.enhanced_checkpoints
                    and self.checkpoint_manager
                    and self.config_hash
                ):
                    try:
                        run_id = (
                            f"multiyear_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                        )
                        checkpoint_data = self.checkpoint_manager.save_checkpoint(
                            year, run_id, self.config_hash
                        )
                        if self.verbose:
                            print(f"   ✅ Enhanced checkpoint saved for year {year}")
                    except Exception as e:
                        print(f"   ⚠️ Enhanced checkpoint failed for year {year}: {e}")
                        # Fall back to legacy checkpoint
                        self._write_checkpoint(
                            WorkflowCheckpoint(
                                year,
                                WorkflowStage.CLEANUP,
                                datetime.utcnow().isoformat(),
                                self._state_hash(year),
                            )
                        )
                else:
                    # Legacy checkpoint system
                    self._write_checkpoint(
                        WorkflowCheckpoint(
                            year,
                            WorkflowStage.CLEANUP,
                            datetime.utcnow().isoformat(),
                            self._state_hash(year),
                        )
                    )

                completed_years.append(year)

        # Final multi-year summary using reporter
        reporter = MultiYearReporter(self.db_manager)
        summary = reporter.generate_summary(completed_years)

        # Display comprehensive multi-year summary (matching monolithic script)
        reporter.display_comprehensive_multi_year_summary(completed_years)

        # Persist multi-year CSV summary
        out_csv = (
            self.reports_dir
            / f"multi_year_summary_{completed_years[0]}_{completed_years[-1]}.csv"
        )
        summary.export_csv(out_csv)
        return summary

    def _execute_year_workflow(
        self, year: int, *, fail_on_validation_error: bool
    ) -> None:
        workflow = self._define_year_workflow(year)

        # Optional: clear existing rows for this year based on config.setup
        self._maybe_clear_year_data(year)

        # Ensure seeds are loaded once
        if not self._seeded:
            seed_res = self.dbt_runner.execute_command(["seed"], stream_output=True)
            if not seed_res.success:
                raise PipelineStageError(
                    f"Dbt seed failed with code {seed_res.return_code}"
                )
            self._seeded = True

        # Year 1 registry seeding
        if year == self.config.simulation.start_year:
            self.registry_manager.get_enrollment_registry().create_for_year(year)
            self.registry_manager.get_deferral_registry().create_table()

        for stage in workflow:
            print(f"   📋 Executing stage: {stage.name.value}")
            with time_block(f"stage:{stage.name.value}"):
                self._run_stage_models(stage, year)

            # Comprehensive validation for foundation models
            if stage.name == WorkflowStage.FOUNDATION:
                start_year = self.config.simulation.start_year

                def _chk(conn):
                    baseline = conn.execute(
                        "SELECT COUNT(*) FROM int_baseline_workforce WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    # For years > start_year, baseline lives in start_year; fetch preserved baseline rows
                    preserved_baseline = conn.execute(
                        "SELECT COUNT(*) FROM int_baseline_workforce WHERE simulation_year = ?",
                        [start_year],
                    ).fetchone()[0]
                    compensation = conn.execute(
                        "SELECT COUNT(*) FROM int_employee_compensation_by_year WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    wn = conn.execute(
                        "SELECT COUNT(*) FROM int_workforce_needs WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    wnbl = conn.execute(
                        "SELECT COUNT(*) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    # Epic E039: Employer contribution model validation (eligibility may not be built in FOUNDATION)
                    try:
                        employer_elig = conn.execute(
                            "SELECT COUNT(*) FROM int_employer_eligibility WHERE simulation_year = ?",
                            [year],
                        ).fetchone()[0]
                    except Exception:
                        employer_elig = 0
                    # int_employer_core_contributions is built in STATE_ACCUMULATION, not FOUNDATION
                    try:
                        employer_core = conn.execute(
                            "SELECT COUNT(*) FROM int_employer_core_contributions WHERE simulation_year = ?",
                            [year],
                        ).fetchone()[0]
                    except Exception:
                        # Table doesn't exist yet (expected in foundation stage)
                        employer_core = 0
                    # Diagnostics: hiring demand
                    total_hires_needed = conn.execute(
                        "SELECT COALESCE(MAX(total_hires_needed), 0) FROM int_workforce_needs WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    level_hires_needed = conn.execute(
                        "SELECT COALESCE(SUM(hires_needed), 0) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    return (
                        int(baseline),
                        int(preserved_baseline),
                        int(compensation),
                        int(wn),
                        int(wnbl),
                        int(employer_elig or 0),
                        int(employer_core or 0),
                        int(total_hires_needed or 0),
                        int(level_hires_needed or 0),
                    )

                (
                    baseline_cnt,
                    preserved_baseline_cnt,
                    comp_cnt,
                    wn_cnt,
                    wnbl_cnt,
                    employer_elig_cnt,
                    employer_core_cnt,
                    total_hires_needed,
                    level_hires_needed,
                ) = self.db_manager.execute_with_retry(_chk)
                print(f"   📊 Foundation model validation for year {year}:")
                if year == start_year:
                    print(f"      int_baseline_workforce: {baseline_cnt} rows")
                else:
                    # Baseline is only populated in start_year; show preserved baseline for clarity
                    print(
                        f"      int_baseline_workforce: {baseline_cnt} rows (current year); preserved baseline {preserved_baseline_cnt} rows (start_year={start_year})"
                    )
                print(f"      int_employee_compensation_by_year: {comp_cnt} rows")
                print(f"      int_workforce_needs: {wn_cnt} rows")
                print(f"      int_workforce_needs_by_level: {wnbl_cnt} rows")
                print(
                    f"      int_employer_eligibility: {employer_elig_cnt} rows (not built in FOUNDATION)"
                )
                print(
                    f"      int_employer_core_contributions: {employer_core_cnt} rows (built later in STATE_ACCUMULATION)"
                )
                print(f"      hiring_demand.total_hires_needed: {total_hires_needed}")
                print(f"      hiring_demand.sum_by_level: {level_hires_needed}")

                # Epic E042 Fix: Only validate baseline workforce for first year
                if baseline_cnt == 0 and year == self.config.simulation.start_year:
                    raise PipelineStageError(
                        f"CRITICAL: int_baseline_workforce has 0 rows for year {year}. Check census data processing."
                    )
                elif baseline_cnt == 0 and year > self.config.simulation.start_year:
                    print(
                        f"ℹ️ int_baseline_workforce has 0 rows for year {year} (expected). Baseline is preserved in start_year={start_year} with {preserved_baseline_cnt} rows."
                    )
                if comp_cnt == 0:
                    raise PipelineStageError(
                        f"CRITICAL: int_employee_compensation_by_year has 0 rows for year {year}. Foundation models are broken."
                    )
                if wn_cnt == 0 or wnbl_cnt == 0:
                    raise PipelineStageError(
                        f"CRITICAL: workforce_needs rows={wn_cnt}, by_level rows={wnbl_cnt} for {year}. Hiring will fail."
                    )
                if employer_elig_cnt == 0:
                    print(
                        f"ℹ️ int_employer_eligibility has 0 rows for year {year} (expected before EVENT_GENERATION)."
                    )
                if employer_core_cnt == 0:
                    print(
                        f"ℹ️ int_employer_core_contributions has 0 rows for year {year} (expected; built during STATE_ACCUMULATION)."
                    )
                if total_hires_needed == 0 or level_hires_needed == 0:
                    print(
                        "⚠️ Hiring demand calculated as 0; new hire events will not be generated. Verify target_growth_rate and termination rates."
                    )

            # Post event-generation sanity check: ensure hires materialized and have compensation
            if stage.name == WorkflowStage.EVENT_GENERATION:

                def _ev_chk(conn):
                    hires = conn.execute(
                        "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    demand = conn.execute(
                        "SELECT COALESCE(SUM(hires_needed),0) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    null_comp_hires = conn.execute(
                        "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ? AND compensation_amount IS NULL",
                        [year],
                    ).fetchone()[0]
                    return int(hires), int(demand or 0), int(null_comp_hires)

                (
                    hires_cnt,
                    demand_cnt,
                    null_comp_cnt,
                ) = self.db_manager.execute_with_retry(_ev_chk)
                if demand_cnt > 0 and hires_cnt == 0:
                    print(
                        f"⚠️ Detected 0 hiring events but demand={demand_cnt}. Rebuilding hiring models."
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_hiring_events int_new_hire_termination_events",
                            "--full-refresh",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )
                if hires_cnt > 0 and null_comp_cnt > 0:
                    print(
                        f"⚠️ Detected {null_comp_cnt} hire(s) with NULL compensation. Rebuilding needs_by_level -> hiring."
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_workforce_needs_by_level int_hiring_events",
                            "--full-refresh",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )

            # Post state accumulation check: ensure hires landed in yearly events and match events exist
            if stage.name == WorkflowStage.STATE_ACCUMULATION:

                def _events_chk(conn):
                    hires_in_fact = conn.execute(
                        "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ? AND lower(event_type) = 'hire'",
                        [year],
                    ).fetchone()[0]
                    hires_src = conn.execute(
                        "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    null_comp_hires = conn.execute(
                        "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ? AND compensation_amount IS NULL",
                        [year],
                    ).fetchone()[0]
                    # Check employer match events
                    contrib_with_deferrals = conn.execute(
                        "SELECT COUNT(*) FROM int_employee_contributions WHERE simulation_year = ? AND annual_contribution_amount > 0",
                        [year],
                    ).fetchone()[0]
                    match_events = conn.execute(
                        "SELECT COUNT(*) FROM fct_employer_match_events WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    return (
                        int(hires_in_fact),
                        int(hires_src),
                        int(null_comp_hires),
                        int(contrib_with_deferrals),
                        int(match_events),
                    )

                (
                    hires_in_fact,
                    hires_src,
                    null_comp_cnt,
                    contrib_with_deferrals,
                    match_events,
                ) = self.db_manager.execute_with_retry(_events_chk)

                if hires_src > 0 and hires_in_fact == 0:
                    print(
                        "⚠️ fct_yearly_events missing hire rows; forcing targeted refresh of hires and facts."
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_hiring_events fct_yearly_events fct_workforce_snapshot",
                            "--full-refresh",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )
                if null_comp_cnt > 0:
                    # After fixing compensation, make sure downstream facts/snapshots reflect it
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "fct_yearly_events fct_workforce_snapshot",
                            "--full-refresh",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )

                # Check employer match events
                if contrib_with_deferrals > 0 and match_events == 0:
                    print(
                        f"⚠️ Found {contrib_with_deferrals} employees with contributions but 0 match events."
                    )
                    print("   Suggested checks:")
                    print("   - Verify dbt vars: active_match_formula, match_formulas")
                    print(
                        "   - Check int_employee_match_calculations for non-zero employer_match_amount"
                    )
                    print(
                        "   - Rebuild: dbt run --select int_employee_match_calculations fct_employer_match_events"
                    )

                # Epic E042 Guardrail: ensure contributions are populated when deferral state exists
                def _contrib_guard(conn):
                    dr_cnt = conn.execute(
                        "SELECT COUNT(*) FROM int_deferral_rate_state_accumulator_v2 WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    comp_cnt = conn.execute(
                        "SELECT COUNT(*) FROM int_employee_compensation_by_year WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    overlap = conn.execute(
                        """
                        WITH dr AS (
                          SELECT employee_id FROM int_deferral_rate_state_accumulator_v2 WHERE simulation_year = ?
                        ), wf AS (
                          SELECT employee_id FROM int_employee_compensation_by_year WHERE simulation_year = ?
                        )
                        SELECT COUNT(*) FROM (
                          SELECT employee_id FROM dr INTERSECT SELECT employee_id FROM wf
                        )
                        """,
                        [year, year],
                    ).fetchone()[0]
                    contrib_rows, contrib_sum = conn.execute(
                        "SELECT COUNT(*), COALESCE(SUM(annual_contribution_amount), 0) FROM int_employee_contributions WHERE simulation_year = ?",
                        [year],
                    ).fetchone()
                    return (
                        int(dr_cnt),
                        int(comp_cnt),
                        int(overlap),
                        int(contrib_rows),
                        float(contrib_sum or 0.0),
                    )

                (
                    dr_cnt,
                    comp_cnt,
                    overlap_cnt,
                    contrib_rows,
                    contrib_sum,
                ) = self.db_manager.execute_with_retry(_contrib_guard)

                if dr_cnt > 0 and (
                    overlap_cnt == 0 or contrib_rows == 0 or contrib_sum == 0.0
                ):
                    print(
                        f"⚠️ Detected deferral state ({dr_cnt}) but no contribution output (rows={contrib_rows}, sum={contrib_sum:.2f}, overlap={overlap_cnt}). Rebuilding staging → compensation → deferral_state → contributions."
                    )
                    # Ensure Year 1 NH staging is present, then rebuild compensation and contributions
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_new_hire_compensation_staging int_employee_compensation_by_year",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_deferral_rate_state_accumulator_v2",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_employee_contributions fct_workforce_snapshot",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )

            # Registry updates after events/state accumulation
            if stage.name == WorkflowStage.EVENT_GENERATION:
                self.registry_manager.get_enrollment_registry().update_post_year(year)
            if stage.name == WorkflowStage.STATE_ACCUMULATION:
                self.registry_manager.get_deferral_registry().update_post_year(year)

            # Stage-level validation hook
            if stage.name in (
                WorkflowStage.STATE_ACCUMULATION,
                WorkflowStage.VALIDATION,
            ):
                dv_results = self.validator.validate_year_results(year)
                if fail_on_validation_error and any(
                    (not r.passed and r.severity.value == "error") for r in dv_results
                ):
                    raise PipelineStageError(
                        f"Validation errors detected for year {year}"
                    )

        # Reporting per year
        auditor = YearAuditor(self.db_manager, self.validator)
        report = auditor.generate_report(year)
        report.export_json(self.reports_dir / f"year_{year}.json")

        # Display detailed year audit (matching monolithic script)
        auditor.generate_detailed_year_audit(year)

        # Final sanity checks handled by reporting/validator

    def _run_stage_models(self, stage: StageDefinition, year: int) -> None:
        if not stage.models:
            return
        # Run event generation and state accumulation sequentially to enforce order
        if stage.name in (
            WorkflowStage.EVENT_GENERATION,
            WorkflowStage.STATE_ACCUMULATION,
        ):
            setup = getattr(self.config, "setup", None)
            force_full_refresh = bool(
                isinstance(setup, dict)
                and setup.get("clear_tables")
                and setup.get("clear_mode", "all").lower() == "all"
            )

            for model in stage.models:
                selection = ["run", "--select", model]
                # Special case: always full-refresh models that have schema issues or self-references
                if (
                    model
                    in [
                        "int_workforce_snapshot_optimized",
                        "int_deferral_rate_escalation_events",
                    ]
                    or force_full_refresh
                ):
                    selection.append("--full-refresh")
                    if self.verbose:
                        if model == "int_workforce_snapshot_optimized":
                            reason = "schema compatibility"
                        elif model == "int_deferral_rate_escalation_events":
                            reason = "self-reference incremental"
                        else:
                            reason = "clear_mode=all"
                        print(
                            f"   🔄 Rebuilding {model} with --full-refresh ({reason}) for year {year}"
                        )
                res = self.dbt_runner.execute_command(
                    selection,
                    simulation_year=year,
                    dbt_vars=self._dbt_vars,
                    stream_output=True,
                )
                if not res.success:
                    raise PipelineStageError(
                        f"Dbt failed on model {model} in stage {stage.name.value} with code {res.return_code}"
                    )
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
                raise PipelineStageError(
                    f"Some models failed in stage {stage.name.value}: {[f.command for f in failed]}"
                )
        else:
            # Run as a single selection for consistent dependency behavior
            selection = ["run", "--select", " ".join(stage.models)]
            # Optimization: Only use --full-refresh for FOUNDATION on first year or when clear_mode == 'all'
            if stage.name == WorkflowStage.FOUNDATION:
                setup = getattr(self.config, "setup", None)
                clear_mode = (
                    isinstance(setup, dict) and setup.get("clear_mode", "all").lower()
                ) or "all"
                if year == self.config.simulation.start_year or clear_mode == "all":
                    selection.append("--full-refresh")
                    if self.verbose:
                        print(
                            f"   🔄 Running {stage.name.value} with --full-refresh (year={year}, clear_mode={clear_mode})"
                        )
            res = self.dbt_runner.execute_command(
                selection,
                simulation_year=year,
                dbt_vars=self._dbt_vars,
                stream_output=True,
            )
            if not res.success:
                raise PipelineStageError(
                    f"Dbt failed in stage {stage.name.value} with code {res.return_code}"
                )

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
            tables = [
                r[0]
                for r in conn.execute(
                    """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
                """
                ).fetchall()
            ]
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
            print(
                f"🧹 Cleared year {year} rows in {cleared} table(s) per setup.clear_table_patterns"
            )

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
            tables = [
                r[0]
                for r in conn.execute(
                    """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
                ).fetchall()
            ]
            cleared = 0
            for t in tables:
                if not _should_clear(t):
                    continue
                conn.execute(f"DELETE FROM {t}")
                cleared += 1
            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared:
            print(
                f"🧹 Full reset: cleared all rows in {cleared} table(s) per setup.clear_table_patterns"
            )

    def _clear_year_fact_rows(self, year: int) -> None:
        """Idempotency guard: remove current-year rows in core fact tables before rebuild.

        This avoids duplicate events/snapshots when event sequencing changes between runs.
        """

        def _run(conn):
            for table in (
                "fct_yearly_events",
                "fct_workforce_snapshot",
                "fct_employer_match_events",
            ):
                try:
                    conn.execute(
                        f"DELETE FROM {table} WHERE simulation_year = ?", [year]
                    )
                except Exception:
                    # Table may not exist yet; ignore
                    pass
            return True

        try:
            self.db_manager.execute_with_retry(_run)
        except Exception:
            pass

    def _define_year_workflow(self, year: int) -> List[StageDefinition]:
        # Align initialization with working runner: broader staging on first year
        if year == self.config.simulation.start_year:
            initialization_models = [
                "staging.*",
                "int_baseline_workforce",
            ]
        else:
            initialization_models = [
                "int_active_employees_prev_year_snapshot",
            ]

        # Epic E042 Fix: Conditional foundation models to preserve historical data
        if year == self.config.simulation.start_year:
            # Year 1: Include baseline workforce (created from census)
            # Ensure new-hire staging is built so NH_YYYY_* appear in compensation
            foundation_models = [
                "int_baseline_workforce",
                "int_new_hire_compensation_staging",
                "int_employee_compensation_by_year",
                "int_effective_parameters",
                "int_workforce_needs",
                "int_workforce_needs_by_level",
            ]
        else:
            # Year 2+: Skip baseline workforce (use incremental data preservation)
            # int_baseline_workforce is incremental and preserves Year 1 data
            foundation_models = [
                "int_employee_compensation_by_year",
                "int_effective_parameters",
                "int_workforce_needs",
                "int_workforce_needs_by_level",
            ]

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
                models=foundation_models,
                validation_rules=["row_count_drift", "compensation_reasonableness"],
            ),
            StageDefinition(
                name=WorkflowStage.EVENT_GENERATION,
                dependencies=[WorkflowStage.FOUNDATION],
                # Match working runner ordering exactly for determinism
                models=[
                    # E049: Ensure synthetic baseline enrollment events are built in the first year
                    # so census deferral rates feed the state accumulator and snapshot participation.
                    *(
                        ["int_synthetic_baseline_enrollment_events"]
                        if year == self.config.simulation.start_year
                        else []
                    ),
                    "int_termination_events",
                    "int_hiring_events",
                    "int_new_hire_termination_events",
                    # Build employer eligibility after new-hire terminations to ensure flags are available
                    "int_employer_eligibility",
                    "int_hazard_promotion",
                    "int_hazard_merit",
                    "int_promotion_events",
                    "int_merit_events",
                    "int_eligibility_determination",
                    "int_voluntary_enrollment_decision",
                    "int_enrollment_events",
                    "int_deferral_rate_escalation_events",
                ],
                validation_rules=["hire_termination_ratio", "event_sequence"],
                parallel_safe=False,
            ),
            StageDefinition(
                name=WorkflowStage.STATE_ACCUMULATION,
                dependencies=[WorkflowStage.EVENT_GENERATION],
                models=[
                    "fct_yearly_events",
                    # Build proration snapshot before contributions so all bases are prorated
                    "int_workforce_snapshot_optimized",
                    "int_enrollment_state_accumulator",
                    "int_deferral_rate_state_accumulator_v2",
                    "int_deferral_escalation_state_accumulator",
                    # Build employer contributions after contributions are computed to ensure proration
                    "int_employee_contributions",
                    "int_employer_core_contributions",
                    "int_employee_match_calculations",
                    "fct_employer_match_events",
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
            print(
                f"⚠️ fct_workforce_snapshot has 0 rows for {year}; verify upstream models and vars"
            )

    def _write_checkpoint(self, ckpt: WorkflowCheckpoint) -> None:
        path = self.checkpoints_dir / f"year_{ckpt.year}.json"
        with open(path, "w") as fh:
            json.dump(
                {
                    "year": ckpt.year,
                    "stage": ckpt.stage.value,
                    "timestamp": ckpt.timestamp,
                    "state_hash": ckpt.state_hash,
                },
                fh,
            )

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

    def _calculate_config_hash(self) -> str:
        """Calculate hash of current configuration for checkpoint validation"""
        import hashlib

        # Try to hash the configuration file
        config_path = Path("config/simulation_config.yaml")
        if config_path.exists():
            try:
                config_content = config_path.read_text()
                return hashlib.sha256(config_content.encode("utf-8")).hexdigest()
            except Exception:
                pass

        # Fallback: hash the config object's dump
        try:
            config_dict = self.config.model_dump()
            config_str = json.dumps(config_dict, sort_keys=True)
            return hashlib.sha256(config_str.encode("utf-8")).hexdigest()
        except Exception:
            return "unknown"
