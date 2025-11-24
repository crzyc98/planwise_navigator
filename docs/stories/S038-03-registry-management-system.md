# Story S038-03: Registry Management System

**Epic**: E038 - PlanAlign Orchestrator Refactoring & Modularization
**Story Points**: 8
**Priority**: High
**Status**: 🟠 In Progress
**Dependencies**: S038-01 (Core Infrastructure Setup)
**Assignee**: Development Team

---

## 🎯 **Goal**

Refactor registry management into a dedicated module with clean interfaces for enrollment and deferral escalation registries, providing type-safe operations and automated integrity validation.

## 📋 **User Story**

As a **developer** working with multi-year simulations,
I want **clean, reliable interfaces for managing enrollment and deferral registries**
So that **I can prevent duplicate enrollments and maintain consistent state across simulation years**.

## 🛠 **Technical Tasks**

### **Task 1: Create Registry Base Classes**
- Design abstract `Registry` interface with common patterns
- Implement `EnrollmentRegistry` class for enrollment state management
- Implement `DeferralEscalationRegistry` class for deferral tracking
- Add registry integrity validation and consistency checks

### **Task 2: Abstract SQL Generation**
- Create SQL template system for registry operations
- Abstract CREATE, INSERT, UPDATE operations behind clean APIs
- Implement cross-year state management logic
- Add support for registry schema evolution

### **Task 3: Migration & Testing**
- Migrate all registry functions from existing `run_multi_year.py`
- Create comprehensive unit tests for all registry operations
- Add integration tests with real database scenarios
- Implement automated integrity validation

## ✅ **Acceptance Criteria**

### **Functional Requirements**
- ✅ Registry classes provide type-safe interfaces
- ✅ Automated integrity validation and consistency checking
- ✅ SQL generation abstracted behind clean APIs
- ✅ Cross-year state management properly handled

### **Quality Requirements**
- ✅ 95%+ test coverage including error scenarios
- ✅ Registry operations are atomic and transactional
- ✅ Clear error messages for integrity violations
- ✅ Performance maintained or improved vs existing implementation

### **Integration Requirements**
- ✅ Works with existing database schema without changes
- ✅ Maintains compatibility with current registry usage patterns
- ✅ Supports future registry schema evolution

## 🧪 **Testing Strategy**

### **Unit Tests**
```python
# test_registries.py
def test_enrollment_registry_create_for_first_year()
def test_enrollment_registry_update_post_year()
def test_deferral_registry_escalation_tracking()
def test_registry_integrity_validation()
def test_cross_year_state_consistency()
def test_registry_sql_generation()
def test_concurrent_registry_access()
```

### **Integration Tests**
- Create and update registries with real database
- Validate multi-year state transitions
- Test registry recovery from corrupted state
- Verify performance with large datasets

## 📊 **Definition of Done**

- [x] `registries.py` module created with registry classes and templates
- [ ] All registry functions migrated from existing code
- [x] SQL generation abstracted behind clean APIs
- [x] Comprehensive integrity validation implemented (initial checks)
- [ ] Unit and integration tests achieve 95%+ coverage
- [x] Documentation complete with usage examples
- [ ] Performance benchmarks show maintained or improved speed
- [ ] Code review completed and approved

## 🔗 **Dependencies**

### **Upstream Dependencies**
- **S038-01**: Requires `utils.py` for database connection management

### **Downstream Dependencies**
- **S038-06** (Pipeline Orchestration): Will use registries for state management
- **Future enrollment/deferral features**: Will extend registry interfaces

## 📝 **Implementation Notes**

### **Registry Interface Design**
```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import date

@dataclass
class RegistryValidationResult:
    is_valid: bool
    errors: List[str]
    warnings: List[str]

class Registry(ABC):
    """Abstract base class for all registries."""

    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager

    @abstractmethod
    def create_table(self) -> bool:
        """Create registry table if it doesn't exist."""

    @abstractmethod
    def validate_integrity(self) -> RegistryValidationResult:
        """Validate registry integrity and consistency."""

class EnrollmentRegistry(Registry):
    """Manages enrollment state across simulation years."""

    def create_for_year(self, year: int) -> bool:
        """Create or update enrollment registry for specified year."""

    def update_post_year(self, year: int) -> bool:
        """Update registry with enrollments from completed year."""

    def get_enrolled_employees(self, year: int) -> List[str]:
        """Get list of enrolled employee IDs for specified year."""

    def is_employee_enrolled(self, employee_id: str, year: int) -> bool:
        """Check if employee is enrolled as of specified year."""

class DeferralEscalationRegistry(Registry):
    """Manages deferral escalation state across simulation years."""

    def update_post_year(self, year: int) -> bool:
        """Update registry with escalations from completed year."""

    def get_escalation_participants(self, year: int) -> List[str]:
        """Get employees participating in auto-escalation."""

    def get_escalation_count(self, employee_id: str) -> int:
        """Get total escalation count for employee."""
```

### **SQL Template System**
```python
class SQLTemplateManager:
    """Manages SQL templates for registry operations."""

    ENROLLMENT_REGISTRY_CREATE = """
    CREATE TABLE IF NOT EXISTS enrollment_registry (
        employee_id VARCHAR PRIMARY KEY,
        first_enrollment_date DATE,
        first_enrollment_year INTEGER,
        enrollment_source VARCHAR,
        is_enrolled BOOLEAN,
        last_updated TIMESTAMP
    )
    """

    ENROLLMENT_REGISTRY_BASELINE = """
    INSERT INTO enrollment_registry
    SELECT DISTINCT
        employee_id,
        employee_enrollment_date AS first_enrollment_date,
        {year} AS first_enrollment_year,
        'baseline' AS enrollment_source,
        true AS is_enrolled,
        CURRENT_TIMESTAMP AS last_updated
    FROM int_baseline_workforce
    WHERE employment_status = 'active'
      AND employee_enrollment_date IS NOT NULL
      AND employee_id IS NOT NULL
    """

    def render_template(self, template: str, **kwargs) -> str:
        """Render SQL template with provided variables."""
        return template.format(**kwargs)
```

### **Integrity Validation System**
```python
class RegistryValidator:
    """Validates registry integrity and consistency."""

    def validate_enrollment_registry(self, year: int) -> RegistryValidationResult:
        """Validate enrollment registry for specified year."""
        errors = []
        warnings = []

        with self.db_manager.get_connection() as conn:
            # Check for orphaned enrollments
            orphaned = conn.execute("""
                SELECT COUNT(*) FROM enrollment_registry er
                WHERE NOT EXISTS (
                    SELECT 1 FROM fct_yearly_events fye
                    WHERE fye.employee_id = er.employee_id
                    AND fye.event_type = 'enrollment'
                )
            """).fetchone()[0]

            if orphaned > 0:
                errors.append(f"{orphaned} orphaned enrollments found")

            # Check for duplicate enrollments
            duplicates = conn.execute("""
                SELECT employee_id, COUNT(*)
                FROM enrollment_registry
                GROUP BY employee_id
                HAVING COUNT(*) > 1
            """).fetchall()

            if duplicates:
                errors.append(f"{len(duplicates)} duplicate employee registrations")

        return RegistryValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
```

### **Transactional Operations**
```python
class TransactionalRegistry:
    """Mixin for atomic registry operations."""

    def execute_transaction(self, operations: List[str]) -> bool:
        """Execute multiple registry operations atomically."""
        with self.db_manager.transaction() as conn:
            try:
                for sql in operations:
                    conn.execute(sql)
                return True
            except Exception as e:
                # Transaction automatically rolled back
                logger.error(f"Registry transaction failed: {e}")
                return False
```

### **Registry Factory Pattern**
```python
class RegistryManager:
    """Factory and coordinator for all registries."""

    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager
        self._enrollment_registry = None
        self._deferral_registry = None

    def get_enrollment_registry(self) -> EnrollmentRegistry:
        """Get or create enrollment registry instance."""
        if self._enrollment_registry is None:
            self._enrollment_registry = EnrollmentRegistry(self.db_manager)
        return self._enrollment_registry

    def get_deferral_registry(self) -> DeferralEscalationRegistry:
        """Get or create deferral escalation registry instance."""
        if self._deferral_registry is None:
            self._deferral_registry = DeferralEscalationRegistry(self.db_manager)
        return self._deferral_registry

    def validate_all_registries(self, year: int) -> Dict[str, RegistryValidationResult]:
        """Validate all registries for specified year."""
        return {
            'enrollment': self.get_enrollment_registry().validate_integrity(),
            'deferral': self.get_deferral_registry().validate_integrity()
        }
```

### 🔧 Implementation Progress

- Added `planalign_orchestrator/registries.py` implementing:
  - `Registry`, `EnrollmentRegistry`, `DeferralEscalationRegistry`, `RegistryManager`
  - `SQLTemplateManager` with create/insert templates and event-based updates
  - `RegistryValidationResult` and validation methods
- Added tests in `tests/test_registries.py` covering baseline creation, event updates, deferral escalation, integrity checks, and SQL templating.

---

**This story provides robust, maintainable registry management with clear interfaces, automated validation, and support for future registry evolution.**

## 📘 **Usage Examples**

```python
from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.registries import RegistryManager

db = DatabaseConnectionManager()  # simulation.duckdb
registries = RegistryManager(db)

# Enrollment registry lifecycle
enr = registries.get_enrollment_registry()
enr.create_table()
enr.create_for_year(2025)        # seed from baseline
enr.update_post_year(2025)       # add enrollments from events

active = enr.get_enrolled_employees(2025)
assert enr.is_employee_enrolled("EMP_001", 2026) in (True, False)

validation = enr.validate_integrity()
if not validation.is_valid:
    print("Integrity issues:", validation.errors)

# Deferral escalation registry
defr = registries.get_deferral_registry()
defr.create_table()
defr.update_post_year(2025)
count = defr.get_escalation_count("EMP_001")
participants = defr.get_escalation_participants(2025)
```
