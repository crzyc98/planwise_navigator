# Data Model: Temporal State Accumulator Contract

**Feature**: 007-state-accumulator-contract
**Date**: 2025-12-14

## Entity Overview

This feature introduces three core entities for formalizing the temporal state accumulator pattern:

```
┌─────────────────────────────┐
│  StateAccumulatorContract   │
│  (Pydantic model)           │
├─────────────────────────────┤
│ + model_name: str           │
│ + table_name: str           │
│ + prior_year_column: str    │
│ + start_year_source: str    │
│ + description: str?         │
└─────────────────────────────┘
            │
            │ registered in
            ▼
┌─────────────────────────────┐
│  StateAccumulatorRegistry   │
│  (Singleton)                │
├─────────────────────────────┤
│ + _contracts: Dict          │
│ + register(contract)        │
│ + get(model_name)           │
│ + list_all()                │
│ + get_registered_tables()   │
└─────────────────────────────┘
            │
            │ used by
            ▼
┌─────────────────────────────┐
│  YearDependencyValidator    │
│  (Stateless validator)      │
├─────────────────────────────┤
│ + db_manager: DBConnMgr     │
│ + start_year: int           │
│ + validate_year_deps(year)  │
│ + get_missing_years(year)   │
│ + validate_checkpoint(year) │
└─────────────────────────────┘
```

---

## Entity: StateAccumulatorContract

### Purpose
Defines the contract that all temporal state accumulator models must implement. Used for registration and validation.

### Fields

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| `model_name` | `str` | Yes | dbt model name (e.g., `int_enrollment_state_accumulator`) | Non-empty, starts with `int_` |
| `table_name` | `str` | Yes | Database table name (usually same as model_name) | Non-empty |
| `prior_year_column` | `str` | Yes | Column used for year filtering | Default: `simulation_year` |
| `start_year_source` | `str` | Yes | Model used for initial state | e.g., `int_baseline_workforce` |
| `description` | `str` | No | Human-readable description | Optional |

### Pydantic Model Definition

```python
from pydantic import BaseModel, Field, field_validator

class StateAccumulatorContract(BaseModel):
    """Contract defining temporal state accumulator requirements."""

    model_name: str = Field(
        ...,
        description="dbt model name implementing the accumulator pattern"
    )
    table_name: str = Field(
        ...,
        description="Database table name for the accumulator"
    )
    prior_year_column: str = Field(
        default="simulation_year",
        description="Column used for year-based filtering"
    )
    start_year_source: str = Field(
        ...,
        description="Model providing initial state for start year"
    )
    description: str = Field(
        default="",
        description="Human-readable description of the accumulator"
    )

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        if not v:
            raise ValueError("model_name cannot be empty")
        if not v.startswith("int_"):
            raise ValueError("model_name must start with 'int_' prefix")
        return v

    @field_validator("table_name")
    @classmethod
    def validate_table_name(cls, v: str) -> str:
        if not v:
            raise ValueError("table_name cannot be empty")
        return v
```

### Validation Rules

1. `model_name` must be non-empty and start with `int_` (intermediate model convention)
2. `table_name` must be non-empty
3. `prior_year_column` defaults to `simulation_year` if not specified
4. `start_year_source` must reference an existing model name

---

## Entity: StateAccumulatorRegistry

### Purpose
Singleton registry that tracks all registered state accumulator contracts and provides lookup methods for validation.

### Class Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `_contracts` | `Dict[str, StateAccumulatorContract]` | Map of model_name to contract |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register` | `(contract: StateAccumulatorContract) -> None` | Register a new accumulator contract |
| `get` | `(model_name: str) -> StateAccumulatorContract` | Get contract by model name |
| `list_all` | `() -> List[str]` | List all registered model names |
| `get_registered_tables` | `() -> List[str]` | Get all registered table names |
| `clear` | `() -> None` | Clear all registrations (testing only) |

### Singleton Pattern

```python
class StateAccumulatorRegistry:
    """Centralized registry for temporal state accumulator contracts."""

    _contracts: Dict[str, StateAccumulatorContract] = {}

    @classmethod
    def register(cls, contract: StateAccumulatorContract) -> None:
        if contract.model_name in cls._contracts:
            raise ValueError(f"Model '{contract.model_name}' already registered")
        cls._contracts[contract.model_name] = contract

    @classmethod
    def get(cls, model_name: str) -> StateAccumulatorContract:
        if model_name not in cls._contracts:
            available = ", ".join(sorted(cls._contracts.keys())) or "(none)"
            raise KeyError(f"Model '{model_name}' not registered. Available: [{available}]")
        return cls._contracts[model_name]

    @classmethod
    def list_all(cls) -> List[str]:
        return sorted(cls._contracts.keys())

    @classmethod
    def get_registered_tables(cls) -> List[str]:
        return [c.table_name for c in cls._contracts.values()]

    @classmethod
    def clear(cls) -> None:
        cls._contracts.clear()
```

---

## Entity: YearDependencyValidator

### Purpose
Validates that year dependencies are satisfied before STATE_ACCUMULATION stage execution.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `db_manager` | `DatabaseConnectionManager` | Database connection for queries |
| `start_year` | `int` | Configured simulation start year |

### Methods

| Method | Signature | Description | Raises |
|--------|-----------|-------------|--------|
| `validate_year_dependencies` | `(year: int) -> None` | Validate prior year data exists | `YearDependencyError` |
| `get_missing_years` | `(year: int) -> Dict[str, List[int]]` | Get missing years per accumulator | N/A |
| `validate_checkpoint_dependencies` | `(checkpoint_year: int) -> None` | Validate full dependency chain | `YearDependencyError` |

### Validation Logic

```python
class YearDependencyValidator:
    """Validates temporal dependencies before state accumulation."""

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        start_year: int
    ):
        self.db_manager = db_manager
        self.start_year = start_year

    def validate_year_dependencies(self, year: int) -> None:
        """Validate that prior year data exists for all accumulators.

        Args:
            year: The simulation year about to execute

        Raises:
            YearDependencyError: If prior year data is missing
        """
        # Start year has no prior dependency
        if year == self.start_year:
            return

        missing = self.get_missing_years(year)
        if missing:
            raise YearDependencyError(
                year=year,
                missing_tables=missing,
                start_year=self.start_year
            )

    def get_missing_years(self, year: int) -> Dict[str, int]:
        """Check which accumulators are missing prior year data.

        Returns:
            Dict mapping table_name to row count (0 if missing)
        """
        missing = {}
        prior_year = year - 1

        for contract in StateAccumulatorRegistry._contracts.values():
            def _check(conn):
                result = conn.execute(
                    f"SELECT COUNT(*) FROM {contract.table_name} "
                    f"WHERE {contract.prior_year_column} = ?",
                    [prior_year]
                ).fetchone()[0]
                return int(result)

            count = self.db_manager.execute_with_retry(_check)
            if count == 0:
                missing[contract.table_name] = 0

        return missing
```

---

## Entity: YearDependencyError

### Purpose
Exception raised when year dependency validation fails, providing actionable debugging information.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `year` | `int` | Year that failed validation |
| `missing_tables` | `Dict[str, int]` | Tables with missing data |
| `start_year` | `int` | Configured start year |
| `message` | `str` | Human-readable error message |
| `resolution_hint` | `str` | Suggested fix |

### Error Format

```python
class YearDependencyError(NavigatorError):
    """Raised when temporal year dependencies are not satisfied."""

    def __init__(
        self,
        year: int,
        missing_tables: Dict[str, int],
        start_year: int
    ):
        self.year = year
        self.missing_tables = missing_tables
        self.start_year = start_year

        # Build error message
        tables_list = "\n".join(
            f"  - {table} (0 rows for year {year - 1})"
            for table in sorted(missing_tables.keys())
        )

        # Build year sequence hint
        sequence = " → ".join(str(y) for y in range(start_year, year + 1))

        message = (
            f"Year {year} depends on year {year - 1} data which has not been executed.\n\n"
            f"Missing data for accumulators:\n{tables_list}\n\n"
            f"Resolution: Run years in sequence: {sequence}\n"
            f"            Or use --start-year {year - 1} if resuming from checkpoint."
        )

        super().__init__(
            message=message,
            error_code="YEAR_DEPENDENCY_VIOLATION",
            resolution_hint=f"Execute year {year - 1} before year {year}"
        )
```

---

## Registered Accumulators (Initial)

### int_enrollment_state_accumulator

```python
StateAccumulatorContract(
    model_name="int_enrollment_state_accumulator",
    table_name="int_enrollment_state_accumulator",
    prior_year_column="simulation_year",
    start_year_source="int_baseline_workforce",
    description="Tracks employee enrollment state across simulation years"
)
```

### int_deferral_rate_state_accumulator

```python
StateAccumulatorContract(
    model_name="int_deferral_rate_state_accumulator",
    table_name="int_deferral_rate_state_accumulator",
    prior_year_column="simulation_year",
    start_year_source="int_employee_compensation_by_year",
    description="Tracks employee deferral rate state across simulation years"
)
```

---

## Relationships

```
StateAccumulatorContract ──── registered in ────► StateAccumulatorRegistry
                                                         │
                                                         │ queries
                                                         ▼
YearDependencyValidator ──── validates against ────► DuckDB Tables
         │
         │ raises on failure
         ▼
YearDependencyError
```

---

## State Transitions

### StateAccumulatorRegistry Lifecycle

```
[Empty] ──register()──► [Has Contracts] ──clear()──► [Empty]
                              │
                              │ get()/list_all()
                              ▼
                        [Returns Data]
```

### YearDependencyValidator Flow

```
validate_year_dependencies(year)
         │
         ├── year == start_year? ──► Return (no validation needed)
         │
         ├── Query each registered table
         │         │
         │         ├── COUNT > 0? ──► Continue
         │         │
         │         └── COUNT == 0? ──► Add to missing
         │
         └── Any missing? ──► Raise YearDependencyError
                    │
                    └── None missing? ──► Return (validation passed)
```
