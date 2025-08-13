Navigator Orchestrator
======================

Lightweight core package providing config, utility, dbt orchestration, registry management, and validation helpers for the PlanWise Navigator pipeline.

Modules
- `config`: Typed config models and loader with env overrides; `to_dbt_vars` for dbt.
- `utils`: `ExecutionMutex`, `DatabaseConnectionManager`, and `time_block` timing.
- `dbt_runner`: `DbtRunner` with streaming, retry/backoff, and parallel execution.
- `registries`: Enrollment and deferral escalation registries with integrity checks.
- `validation`: Rule-based validation engine and built-in rules.

Quickstart
- Load config and map to dbt vars:
  ```python
  from navigator_orchestrator.config import load_simulation_config, to_dbt_vars
  cfg = load_simulation_config()
  vars_dict = to_dbt_vars(cfg)
  ```
- Run dbt with streaming output:
  ```python
  from navigator_orchestrator.dbt_runner import DbtRunner
  runner = DbtRunner()  # cwd='dbt'
  res = runner.execute_command(["run", "--select", "int_*"], stream_output=True)
  assert res.success
  ```
- Manage registries:
  ```python
  from navigator_orchestrator.utils import DatabaseConnectionManager
  from navigator_orchestrator.registries import RegistryManager
  db = DatabaseConnectionManager()
  regs = RegistryManager(db)
  enr = regs.get_enrollment_registry()
  enr.create_table(); enr.create_for_year(2025); enr.update_post_year(2025)
  ```
- Validate results:
  ```python
  from navigator_orchestrator.validation import DataValidator, HireTerminationRatioRule
  dv = DataValidator(db)
  dv.register_rule(HireTerminationRatioRule())
  report = DataValidator.to_report_dict(dv.validate_year_results(2025))
  ```

Related Stories (S038)
- S038-01: Core Infrastructure Setup
- S038-02: dbt Command Orchestration
- S038-03: Registry Management System
- S038-04: Data Quality & Validation Framework
