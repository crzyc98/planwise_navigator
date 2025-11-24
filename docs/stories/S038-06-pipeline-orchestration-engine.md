# Story S038-06: Pipeline Orchestration Engine

**Epic**: E038 - PlanAlign Orchestrator Refactoring & Modularization
**Story Points**: 8
**Priority**: High
**Status**: 🟠 In Progress
**Dependencies**: S038-01 (Core Infrastructure), S038-02 (dbt Runner), S038-03 (Registry Management), S038-04 (Validation Framework), S038-05 (Reporting)
**Assignee**: Development Team

---

## 🎯 **Goal**

Create the core orchestration engine that coordinates all pipeline components, managing workflow execution, state transitions, and error recovery for multi-year simulations.

## 📋 **User Story**

As a **business analyst** running multi-year workforce simulations,
I want **a reliable orchestration engine that manages complex workflows with clear progress reporting**
So that **I can run simulations confidently with visibility into each step and automatic recovery from failures**.

## 🛠 **Technical Tasks**

### **Task 1: Create Pipeline Orchestration Framework**
- Design `PipelineOrchestrator` class for workflow management
- Implement stage-based execution with dependency tracking
- Create workflow state management and recovery mechanisms
- Add support for multi-year simulation coordination

### **Task 2: Workflow Definition & Execution**
- Define standard simulation workflow stages
- Implement parallel execution where appropriate
- Add checkpoint/restart functionality for long-running simulations
- Create workflow validation and dry-run capabilities

### **Task 3: Integration & Error Recovery**
- Integrate all previous modules (config, dbt_runner, registries, validation, reporting)
- Implement comprehensive error recovery and rollback mechanisms
- Add progress reporting with detailed status updates
- Create workflow audit trail and execution logging

## ✅ **Acceptance Criteria**

### **Functional Requirements**
- ✅ Pipeline orchestrates all simulation stages with proper dependencies
- ✅ Multi-year workflow coordination with state management
- ✅ Checkpoint/restart functionality for interrupted simulations
- ✅ Comprehensive error recovery and rollback capabilities

### **Quality Requirements**
- ✅ 95%+ test coverage including complex workflow scenarios
- ✅ Performance maintained or improved vs existing implementation
- ✅ Reliable progress reporting with accurate status updates
- ✅ Robust handling of partial failures and recovery

### **Integration Requirements**
- ✅ Seamless integration with all orchestrator modules
- ✅ Compatible with existing simulation workflow patterns
- ✅ Supports configuration-driven workflow customization

## 🧪 **Testing Strategy**

### **Unit Tests**
```python
# test_pipeline.py
def test_pipeline_orchestrator_stage_dependencies()
def test_multi_year_workflow_coordination()
def test_checkpoint_restart_functionality()
def test_error_recovery_rollback_mechanisms()
def test_parallel_execution_optimization()
def test_workflow_validation_dry_run()
def test_progress_reporting_accuracy()
```

### **Integration Tests**
- Execute complete multi-year simulation workflows
- Test checkpoint/restart with real database state
- Validate error recovery in various failure scenarios
- Test parallel execution with resource constraints

## 📊 **Definition of Done**

- [x] `pipeline.py` module created with orchestration framework
- [x] Multi-year workflow coordination implemented
- [x] Checkpoint writing and resume baseline (latest-year) support
- [ ] Error recovery and rollback mechanisms tested
- [x] Integration with orchestrator modules (dbt, registries, validation, reporting)
- [ ] Unit and integration tests achieve 95%+ coverage
- [ ] Performance benchmarks show maintained or improved speed
- [x] Documentation complete with workflow examples

### 🔧 Implementation Progress

- Added `planalign_orchestrator/pipeline.py` implementing stage-based orchestration with per-year validation and reporting, registry updates, parallel-safe event generation, and checkpoint files under `.planalign_checkpoints/`.
- Added `tests/test_pipeline.py` covering multi-year coordination, CSV summary export, and checkpoint creation (with a dummy dbt runner).

## 📘 **Usage Examples**

```python
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.dbt_runner import DbtRunner
from planalign_orchestrator.registries import RegistryManager
from planalign_orchestrator.validation import DataValidator, HireTerminationRatioRule, EventSequenceRule
from planalign_orchestrator.pipeline import PipelineOrchestrator

cfg = load_simulation_config()
db = DatabaseConnectionManager()
runner = DbtRunner()
registries = RegistryManager(db)
dv = DataValidator(db)
dv.register_rule(HireTerminationRatioRule())
dv.register_rule(EventSequenceRule())

orchestrator = PipelineOrchestrator(cfg, db, runner, registries, dv)
summary = orchestrator.execute_multi_year_simulation(fail_on_validation_error=False)
print(summary.growth_analysis)
```

## 🔗 **Dependencies**

### **Upstream Dependencies**
- **S038-01**: Requires `utils.py` and `config.py` for foundation
- **S038-02**: Uses `DbtRunner` for model execution
- **S038-03**: Uses registries for state management
- **S038-04**: Uses validation framework for quality checks
- **S038-05**: Uses reporting system for audit results

### **Downstream Dependencies**
- **S038-07** (CLI Interface): Will use pipeline orchestrator
- **S038-08** (Integration): Will validate complete pipeline

## 📝 **Implementation Notes**

### **Pipeline Orchestration Design**
```python
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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
    timestamp: datetime
    state_hash: str
    registry_snapshots: Dict[str, Any]

class PipelineOrchestrator:
    """Main orchestration engine for multi-year simulations."""

    def __init__(
        self,
        config: SimulationConfig,
        db_manager: DatabaseConnectionManager,
        dbt_runner: DbtRunner,
        registry_manager: RegistryManager,
        validator: DataValidator,
        reporter: MultiYearReporter
    ):
        self.config = config
        self.db_manager = db_manager
        self.dbt_runner = dbt_runner
        self.registry_manager = registry_manager
        self.validator = validator
        self.reporter = reporter
        self.checkpoints: List[WorkflowCheckpoint] = []

    def execute_multi_year_simulation(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        resume_from_checkpoint: bool = False
    ) -> MultiYearSummary:
        """Execute complete multi-year simulation workflow."""

        start_year = start_year or self.config.simulation.start_year
        end_year = end_year or self.config.simulation.end_year

        if resume_from_checkpoint:
            last_checkpoint = self._find_last_checkpoint()
            if last_checkpoint:
                start_year = last_checkpoint.year
                self._restore_from_checkpoint(last_checkpoint)

        try:
            for year in range(start_year, end_year + 1):
                print(f"\n🔄 Starting simulation year {year}")
                self._execute_year_workflow(year)
                self._create_checkpoint(year)

            return self._generate_final_report(start_year, end_year)

        except Exception as e:
            self._handle_pipeline_failure(e, year if 'year' in locals() else start_year)
            raise

    def _execute_year_workflow(self, year: int) -> None:
        """Execute workflow for a single simulation year."""

        workflow = self._define_year_workflow(year)

        for stage_def in workflow:
            print(f"   📋 Executing stage: {stage_def.name.value}")

            try:
                self._execute_workflow_stage(year, stage_def)
                self._validate_stage_results(year, stage_def)

            except Exception as e:
                if not self._attempt_stage_recovery(year, stage_def, e):
                    raise PipelineStageError(
                        f"Stage {stage_def.name.value} failed for year {year}: {e}"
                    )
```

### **Workflow Stage Definitions**
```python
def _define_year_workflow(self, year: int) -> List[StageDefinition]:
    """Define the standard workflow for a simulation year."""

    return [
        StageDefinition(
            name=WorkflowStage.INITIALIZATION,
            dependencies=[],
            models=["stg_census_data"],
            validation_rules=["data_freshness_check"]
        ),
        StageDefinition(
            name=WorkflowStage.FOUNDATION,
            dependencies=[WorkflowStage.INITIALIZATION],
            models=[
                "int_baseline_workforce",
                "int_employee_compensation_by_year",
                "int_effective_parameters"
            ],
            validation_rules=["row_count_drift", "compensation_reasonableness"]
        ),
        StageDefinition(
            name=WorkflowStage.EVENT_GENERATION,
            dependencies=[WorkflowStage.FOUNDATION],
            models=[
                "int_workforce_needs",
                "int_workforce_needs_by_level",
                "int_hiring_events",
                "int_termination_events",
                "int_promotion_events",
                "int_merit_events",
                "int_enrollment_events"
            ],
            validation_rules=["hire_termination_ratio", "event_sequence"],
            parallel_safe=True  # These can run in parallel
        ),
        StageDefinition(
            name=WorkflowStage.STATE_ACCUMULATION,
            dependencies=[WorkflowStage.EVENT_GENERATION],
            models=[
                "fct_yearly_events",
                "int_enrollment_state_accumulator",
                "int_deferral_rate_state_accumulator",
                "int_deferral_escalation_state_accumulator"
            ],
            validation_rules=["state_consistency", "accumulator_integrity"]
        ),
        StageDefinition(
            name=WorkflowStage.VALIDATION,
            dependencies=[WorkflowStage.STATE_ACCUMULATION],
            models=["fct_workforce_snapshot", "int_employee_contributions"],
            validation_rules=["workforce_totals", "contribution_limits"]
        ),
        StageDefinition(
            name=WorkflowStage.REPORTING,
            dependencies=[WorkflowStage.VALIDATION],
            models=[],
            validation_rules=[]
        )
    ]
```

## 🧭 **Workflow Stages Summary**

- INITIALIZATION: Runs `stg_census_data`; pre-flight checks and freshness validation.
- FOUNDATION: Builds core intermediates: `int_baseline_workforce`, `int_employee_compensation_by_year`, `int_effective_parameters`.
- EVENT_GENERATION: Generates workforce events (hire, termination, promotion, merit, enrollment). Parallel-safe execution via `DbtRunner.run_models`.
- STATE_ACCUMULATION: Updates `fct_yearly_events` and accumulators (`int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`, `int_deferral_escalation_state_accumulator`).
- VALIDATION: Executes registered rules using `DataValidator` (e.g., ratio, sequence, spike).
- REPORTING: Emits per-year JSON reports and contributes to multi-year CSV summary.

### Configuration knobs
- `simulation.start_year` / `simulation.end_year`: year bounds for orchestration.
- `--fail-on-validation-error`: pipeline flag to stop on ERROR-severity failures.
- `DbtRunner(threads=N)`: control dbt parallelism for heavier stages.


### **Checkpoint & Recovery System**
```python
def _create_checkpoint(self, year: int) -> WorkflowCheckpoint:
    """Create a checkpoint for the completed year."""

    # Generate state hash for integrity checking
    state_hash = self._calculate_state_hash(year)

    # Capture registry snapshots
    registry_snapshots = {
        'enrollment': self.registry_manager.get_enrollment_registry().get_state_snapshot(year),
        'deferral': self.registry_manager.get_deferral_registry().get_state_snapshot(year)
    }

    checkpoint = WorkflowCheckpoint(
        year=year,
        stage=WorkflowStage.REPORTING,  # Completed all stages
        timestamp=datetime.utcnow(),
        state_hash=state_hash,
        registry_snapshots=registry_snapshots
    )

    self.checkpoints.append(checkpoint)
    self._persist_checkpoint(checkpoint)

    return checkpoint

def _restore_from_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
    """Restore pipeline state from checkpoint."""

    print(f"🔄 Restoring from checkpoint: Year {checkpoint.year}")

    # Validate checkpoint integrity
    current_hash = self._calculate_state_hash(checkpoint.year)
    if current_hash != checkpoint.state_hash:
        raise CheckpointCorruptionError(
            f"Checkpoint state hash mismatch for year {checkpoint.year}"
        )

    # Restore registry states
    for registry_name, snapshot in checkpoint.registry_snapshots.items():
        registry = getattr(self.registry_manager, f"get_{registry_name}_registry")()
        registry.restore_from_snapshot(snapshot)

def _attempt_stage_recovery(
    self,
    year: int,
    stage_def: StageDefinition,
    error: Exception
) -> bool:
    """Attempt to recover from stage failure."""

    recovery_strategies = {
        WorkflowStage.EVENT_GENERATION: self._recover_event_generation,
        WorkflowStage.STATE_ACCUMULATION: self._recover_state_accumulation,
        WorkflowStage.VALIDATION: self._recover_validation
    }

    strategy = recovery_strategies.get(stage_def.name)
    if strategy:
        try:
            print(f"🔧 Attempting recovery for stage {stage_def.name.value}")
            strategy(year, error)
            return True
        except Exception as recovery_error:
            print(f"❌ Recovery failed: {recovery_error}")

    return False
```

### **Progress Reporting & Monitoring**
```python
@dataclass
class ExecutionProgress:
    current_year: int
    total_years: int
    current_stage: WorkflowStage
    stages_completed: int
    total_stages: int
    start_time: datetime
    estimated_completion: Optional[datetime]

class ProgressReporter:
    """Provides real-time progress reporting for long-running simulations."""

    def __init__(self, total_years: int, stages_per_year: int):
        self.total_years = total_years
        self.stages_per_year = stages_per_year
        self.start_time = datetime.utcnow()
        self.completed_stages = 0

    def update_progress(
        self,
        year: int,
        stage: WorkflowStage,
        stage_duration: float
    ) -> ExecutionProgress:
        """Update progress and calculate estimated completion."""

        self.completed_stages += 1
        total_stages = self.total_years * self.stages_per_year
        progress_pct = (self.completed_stages / total_stages) * 100

        # Calculate ETA based on average stage duration
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        avg_stage_duration = elapsed / self.completed_stages
        remaining_stages = total_stages - self.completed_stages
        eta = datetime.utcnow() + timedelta(seconds=remaining_stages * avg_stage_duration)

        progress = ExecutionProgress(
            current_year=year,
            total_years=self.total_years,
            current_stage=stage,
            stages_completed=self.completed_stages,
            total_stages=total_stages,
            start_time=self.start_time,
            estimated_completion=eta
        )

        self._print_progress_update(progress, progress_pct)
        return progress

    def _print_progress_update(self, progress: ExecutionProgress, pct: float):
        """Print formatted progress update."""
        elapsed = datetime.utcnow() - progress.start_time
        eta_str = progress.estimated_completion.strftime("%H:%M:%S") if progress.estimated_completion else "Unknown"

        print(f"   📊 Progress: {pct:.1f}% | Year {progress.current_year} | "
              f"Stage: {progress.current_stage.value} | "
              f"Elapsed: {str(elapsed).split('.')[0]} | ETA: {eta_str}")
```

### **Error Handling & Custom Exceptions**
```python
class PipelineError(Exception):
    """Base exception for pipeline operations."""

class PipelineStageError(PipelineError):
    """Error during specific workflow stage execution."""

class CheckpointCorruptionError(PipelineError):
    """Error when checkpoint data is corrupted."""

class WorkflowValidationError(PipelineError):
    """Error during workflow definition validation."""

class StateInconsistencyError(PipelineError):
    """Error when pipeline state becomes inconsistent."""
```

---

**This story provides comprehensive workflow orchestration with checkpoint/restart capabilities, progress monitoring, and robust error recovery for reliable multi-year simulations.**
