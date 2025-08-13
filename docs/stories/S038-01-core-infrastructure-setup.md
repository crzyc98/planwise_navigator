# Story S038-01: Core Infrastructure Setup

**Epic**: E038 - Navigator Orchestrator Refactoring & Modularization
**Story Points**: 5
**Priority**: High
**Status**: 🟠 In Progress
**Dependencies**: None
**Assignee**: Development Team

---

## 🎯 **Goal**

Create foundational modules for configuration and utilities that will serve as the backbone for the new `navigator_orchestrator` package.

## 📋 **User Story**

As a **developer** working on the PlanWise Navigator system,
I want **clean, modular foundation components for configuration and utilities**
So that **I can build other orchestrator modules on a solid, testable foundation**.

## 🛠 **Technical Tasks**

### **Task 1: Create `utils.py` Module**
- Extract `ExecutionMutex` from `shared_utils.py`
- Create `DatabaseConnectionManager` class for DuckDB connections
- Add timing utilities and logging helpers
- Implement retry mechanisms for database operations
- Add connection pooling support

### **Task 2: Create `config.py` Module**
- Design Pydantic models for simulation configuration
- Migrate YAML loading logic from `run_multi_year.py`
- Add configuration validation with clear error messages
- Implement dbt variable mapping functionality
- Support environment variable overrides

### **Task 3: Migration & Testing**
- Migrate core utilities from existing `run_multi_year.py`
- Create comprehensive unit tests for both modules
- Add integration tests with existing configuration files
- Ensure 95%+ test coverage
- Validate performance is maintained

## ✅ **Acceptance Criteria**

### **Functional Requirements**
- ✅ `utils.py` provides database connection management and mutex handling
- ✅ `config.py` loads and validates YAML with type-safe Pydantic models
- ✅ Configuration includes `scenario_id` and `plan_design_id` and validates presence
- ✅ All existing functionality preserved with no regressions

### **Quality Requirements**
- ✅ 95%+ test coverage for both modules
- ✅ All functions have comprehensive docstrings with examples
- ✅ Pass linting, type checking, and security scans
- ✅ Performance within 2% of existing implementation

### **Integration Requirements**
- ✅ Works with existing `simulation_config.yaml` format
- ✅ Compatible with current DuckDB database structure
- ✅ Maintains existing error handling behavior

## 🧪 **Testing Strategy**

### **Unit Tests**
```python
# test_config.py
def test_load_simulation_config_valid_yaml()
def test_config_validation_missing_scenario_id()
def test_dbt_var_mapping_compensation_params()
def test_environment_variable_overrides()

# test_utils.py
def test_database_connection_manager()
def test_execution_mutex_prevents_concurrent_runs()
def test_retry_mechanism_transient_failures()
def test_timing_utilities_accurate_measurement()
```

### **Integration Tests**
- Load existing configuration files successfully
- Database connections work with real DuckDB files
- Mutex prevents actual concurrent simulation runs
- Configuration validation catches real-world issues

## 📊 **Definition of Done**

- [x] `utils.py` module created with core utilities (mutex, DB manager, timing)
- [x] `config.py` module created with Pydantic validation and dbt var mapping
- [ ] Unit tests achieve 95%+ coverage
- [ ] Integration tests validate existing functionality
- [x] Documentation complete with API examples
- [ ] Code review completed and approved
- [ ] Performance benchmarks confirm no regression

### 🔧 Implementation Progress

- Core modules added under `navigator_orchestrator/`:
  - `navigator_orchestrator/utils.py` (ExecutionMutex, DatabaseConnectionManager, `time_block`)
  - `navigator_orchestrator/config.py` (typed loader, env overrides, `to_dbt_vars`)
- Targeted unit tests added:
  - `tests/test_navigator_config.py`
  - `tests/test_navigator_utils.py`
- Backward compatibility preserved with existing YAML in `config/simulation_config.yaml`.

## 📘 **Usage Examples**

```python
# navigator_orchestrator.config
from navigator_orchestrator.config import load_simulation_config, to_dbt_vars

cfg = load_simulation_config()  # reads config/simulation_config.yaml
cfg.require_identifiers()  # optional enforcement for scenario_id/plan_design_id
vars_dict = to_dbt_vars(cfg)

# navigator_orchestrator.utils
from navigator_orchestrator.utils import DatabaseConnectionManager, ExecutionMutex, time_block

db = DatabaseConnectionManager()  # defaults to simulation.duckdb
with db.transaction() as conn:
    conn.execute("SELECT 1")

with ExecutionMutex("sim_run"):
    with time_block("dbt_phase"):
        pass  # run orchestrated phase
```

## 🔗 **Dependencies**

### **Upstream Dependencies**
- None - this is foundational work

### **Downstream Dependencies**
- S038-02 (dbt Command Orchestration) depends on this story
- S038-03 (Registry Management) depends on `utils.py`
- S038-04 (Data Quality Framework) depends on `utils.py`

## 📝 **Implementation Notes**

### **Configuration Schema Design**
```python
class SimulationConfig(BaseModel):
    scenario_id: str = Field(..., min_length=1)
    plan_design_id: str = Field(..., min_length=1)
    simulation: SimulationSettings
    compensation: CompensationSettings
    enrollment: EnrollmentSettings

class SimulationSettings(BaseModel):
    start_year: int = Field(..., ge=2020, le=2030)
    end_year: int = Field(..., ge=2020, le=2040)
    random_seed: int = Field(default=42)
```

### **Database Connection Pattern**
```python
class DatabaseConnectionManager:
    def __init__(self, db_path: Path = Path("simulation.duckdb")):
        self.db_path = db_path

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    @contextmanager
    def transaction(self):
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
```

### **Error Handling Strategy**
- Use custom exception hierarchy for clear error classification
- Provide helpful error messages with suggested resolutions
- Maintain backwards compatibility with existing error patterns

---

**This story establishes the foundational infrastructure that enables clean, testable, and maintainable development of all subsequent orchestrator modules.**
