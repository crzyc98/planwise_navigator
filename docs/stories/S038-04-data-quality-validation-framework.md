# Story S038-04: Data Quality & Validation Framework

**Epic**: E038 - PlanAlign Orchestrator Refactoring & Modularization
**Story Points**: 3
**Priority**: High
**Status**: 🟠 In Progress
**Dependencies**: S038-01 (Core Infrastructure Setup)
**Assignee**: Development Team

---

## 🎯 **Goal**

Create a comprehensive validation and data quality module that provides configurable data quality rules, business rule validation, and anomaly detection for the simulation pipeline.

## 📋 **User Story**

As a **data analyst** using the Fidelity PlanAlign Engine system,
I want **automated data quality validation with configurable rules and clear error reporting**
So that **I can trust simulation results and quickly identify data issues before they impact analysis**.

## 🛠 **Technical Tasks**

### **Task 1: Create Data Quality Framework**
- Design configurable data quality rules and thresholds
- Extract validation logic from existing audit functions
- Implement threshold-based validation with configurable limits
- Add support for custom validation rules

### **Task 2: Business Rule Validation**
- Implement business rule validation with clear error messages
- Add validation for workforce transition rules (hire/termination ratios)
- Validate event sequencing and temporal consistency
- Check for data anomalies and outliers

### **Task 3: Integration & Reporting**
- Integrate validation framework with pipeline execution
- Create validation reports with actionable insights
- Add automated anomaly detection for unusual data patterns
- Support multiple validation severity levels (error, warning, info)

## ✅ **Acceptance Criteria**

### **Functional Requirements**
- ✅ Configurable data quality rules and thresholds
- ✅ Business rule validation with clear error messages
- ✅ Anomaly detection for unusual data patterns
- ✅ Integration with pipeline for automated validation

### **Quality Requirements**
- ✅ 95%+ test coverage including edge cases
- ✅ Fast validation execution (< 5% of total pipeline time)
- ✅ Clear, actionable validation error messages
- ✅ Support for custom validation rules

### **Integration Requirements**
- ✅ Works with existing database schema
- ✅ Integrates with pipeline orchestration
- ✅ Supports multiple output formats for validation reports

## 🧪 **Testing Strategy**

### **Unit Tests**
```python
# test_validation.py
def test_data_quality_rules_configurable_thresholds()
def test_business_rule_validation_hire_termination_ratios()
def test_anomaly_detection_unusual_patterns()
def test_validation_severity_levels()
def test_custom_validation_rule_registration()
def test_validation_report_generation()
```

### **Integration Tests**
- Validate with real simulation data
- Test custom business rules with edge cases
- Verify anomaly detection with known outliers
- Test validation integration with pipeline

## 📊 **Definition of Done**

- [x] `validation.py` module created with validation framework
- [x] Configurable data quality rules implemented
- [x] Business rule validation system working
- [x] Anomaly detection algorithms integrated (event spike)
- [ ] Pipeline integration completed
- [ ] Unit and integration tests achieve 95%+ coverage
- [ ] Validation reports generated in multiple formats
- [x] Documentation complete with rule configuration examples

### 🔧 Implementation Progress

- Added `planalign_orchestrator/validation.py` implementing:
  - Core: `DataValidator`, `ValidationRule` protocol, `ValidationResult`, `ValidationSeverity`
  - Built-ins: `RowCountDriftRule`, `HireTerminationRatioRule`, `EventSequenceRule`, `EventSpikeRule`
  - Reporting helper: `DataValidator.to_report_dict(results)`
- Added tests in `tests/test_validation.py` for:
  - Threshold configuration, ratio rule, spike detection, custom rule registration
  - Severity behavior and report generation

## 🔗 **Dependencies**

### **Upstream Dependencies**
- **S038-01**: Requires `utils.py` for database connections and logging

### **Downstream Dependencies**
- **S038-05** (Reporting): Will use validation results in audit reports
- **S038-06** (Pipeline Orchestration): Will integrate validation into workflow

## 📝 **Implementation Notes**

### **Validation Framework Design**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum

class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class ValidationResult:
    rule_name: str
    severity: ValidationSeverity
    passed: bool
    message: str
    details: Dict[str, Any]
    affected_records: Optional[int] = None

class ValidationRule(ABC):
    """Abstract base class for validation rules."""

    def __init__(self, name: str, severity: ValidationSeverity = ValidationSeverity.ERROR):
        self.name = name
        self.severity = severity

    @abstractmethod
    def validate(self, db_connection, year: int) -> ValidationResult:
        """Execute validation rule and return result."""

class DataValidator:
    """Main validation orchestrator."""

    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager
        self.rules: List[ValidationRule] = []

    def register_rule(self, rule: ValidationRule):
        """Register a validation rule."""
        self.rules.append(rule)

    def validate_year_results(self, year: int) -> List[ValidationResult]:
        """Run all validation rules for specified year."""
        results = []
        with self.db_manager.get_connection() as conn:
            for rule in self.rules:
                try:
                    result = rule.validate(conn, year)
                    results.append(result)
                except Exception as e:
                    results.append(ValidationResult(
                        rule_name=rule.name,
                        severity=ValidationSeverity.ERROR,
                        passed=False,
                        message=f"Validation rule failed: {e}",
                        details={"error": str(e)}
                    ))
        return results

```

## 📘 **Usage Examples**

```python
from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.validation import (
    DataValidator,
    RowCountDriftRule,
    HireTerminationRatioRule,
    EventSequenceRule,
    EventSpikeRule,
)

db = DatabaseConnectionManager()
dv = DataValidator(db)

# Register built-in rules
dv.register_rule(RowCountDriftRule("raw_events", "stg_events", year_column="simulation_year", threshold=0.005))
dv.register_rule(HireTerminationRatioRule(min_ratio=0.3, max_ratio=3.0))
dv.register_rule(EventSequenceRule())
dv.register_rule(EventSpikeRule(spike_ratio=2.0))

# Execute for a year and produce a simple report
results = dv.validate_year_results(2026)
report = DataValidator.to_report_dict(results)
print(report["summary"])  # totals + failures by severity
```

### **Built-in Validation Rules**
```python
class RowCountDriftRule(ValidationRule):
    """Validate row count drift between raw and staged data."""

    def __init__(self, threshold: float = 0.005):
        super().__init__("row_count_drift", ValidationSeverity.ERROR)
        self.threshold = threshold

    def validate(self, conn, year: int) -> ValidationResult:
        # Implementation for row count validation
        raw_count = conn.execute("SELECT COUNT(*) FROM raw_table WHERE year = ?", [year]).fetchone()[0]
        staged_count = conn.execute("SELECT COUNT(*) FROM staged_table WHERE year = ?", [year]).fetchone()[0]

        drift = abs(raw_count - staged_count) / raw_count
        passed = drift <= self.threshold

        return ValidationResult(
            rule_name=self.name,
            severity=self.severity,
            passed=passed,
            message=f"Row count drift: {drift:.3f} ({'PASS' if passed else 'FAIL'})",
            details={
                "raw_count": raw_count,
                "staged_count": staged_count,
                "drift": drift,
                "threshold": self.threshold
            }
        )

class HireTerminationRatioRule(ValidationRule):
    """Validate hire to termination ratios are reasonable."""

    def __init__(self, max_ratio: float = 3.0, min_ratio: float = 0.3):
        super().__init__("hire_termination_ratio", ValidationSeverity.WARNING)
        self.max_ratio = max_ratio
        self.min_ratio = min_ratio

    def validate(self, conn, year: int) -> ValidationResult:
        query = """
        SELECT
            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as hires,
            COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as terminations
        FROM fct_yearly_events
        WHERE simulation_year = ?
        """
        result = conn.execute(query, [year]).fetchone()
        hires, terminations = result

        if terminations == 0:
            ratio = float('inf')
            passed = False
            message = "No terminations found - unusual pattern"
        else:
            ratio = hires / terminations
            passed = self.min_ratio <= ratio <= self.max_ratio
            message = f"Hire/termination ratio: {ratio:.2f} ({'PASS' if passed else 'FAIL'})"

        return ValidationResult(
            rule_name=self.name,
            severity=self.severity,
            passed=passed,
            message=message,
            details={
                "hires": hires,
                "terminations": terminations,
                "ratio": ratio,
                "min_ratio": self.min_ratio,
                "max_ratio": self.max_ratio
            }
        )

class EventSequenceRule(ValidationRule):
    """Validate temporal consistency of events."""

    def __init__(self):
        super().__init__("event_sequence_validation", ValidationSeverity.ERROR)

    def validate(self, conn, year: int) -> ValidationResult:
        # Check for events after termination
        invalid_events = conn.execute("""
            WITH employee_terminations AS (
                SELECT employee_id, MIN(effective_date) as termination_date
                FROM fct_yearly_events
                WHERE event_type = 'termination' AND simulation_year = ?
                GROUP BY employee_id
            )
            SELECT COUNT(*)
            FROM fct_yearly_events fye
            JOIN employee_terminations et ON fye.employee_id = et.employee_id
            WHERE fye.simulation_year = ?
              AND fye.event_type != 'termination'
              AND fye.effective_date > et.termination_date
        """, [year, year]).fetchone()[0]

        passed = invalid_events == 0

        return ValidationResult(
            rule_name=self.name,
            severity=self.severity,
            passed=passed,
            message=f"Event sequence validation: {invalid_events} invalid events",
            details={"invalid_event_count": invalid_events},
            affected_records=invalid_events
        )
```

### **Anomaly Detection System**
```python
class AnomalyDetector:
    """Statistical anomaly detection for simulation data."""

    def detect_compensation_anomalies(self, conn, year: int) -> List[ValidationResult]:
        """Detect unusual compensation patterns."""
        results = []

        # Z-score based outlier detection
        query = """
        WITH compensation_stats AS (
            SELECT
                AVG(compensation_amount) as mean_comp,
                STDDEV(compensation_amount) as std_comp
            FROM fct_yearly_events
            WHERE event_type IN ('hire', 'raise') AND simulation_year = ?
        ),
        compensation_zscore AS (
            SELECT
                employee_id,
                compensation_amount,
                ABS(compensation_amount - cs.mean_comp) / cs.std_comp as z_score
            FROM fct_yearly_events fye
            CROSS JOIN compensation_stats cs
            WHERE fye.event_type IN ('hire', 'raise') AND fye.simulation_year = ?
        )
        SELECT COUNT(*) FROM compensation_zscore WHERE z_score > 3
        """

        outliers = conn.execute(query, [year, year]).fetchone()[0]

        results.append(ValidationResult(
            rule_name="compensation_anomaly_detection",
            severity=ValidationSeverity.WARNING,
            passed=outliers < 10,  # Threshold for concern
            message=f"Compensation anomalies detected: {outliers} outliers",
            details={"outlier_count": outliers, "z_score_threshold": 3}
        ))

        return results
```

### **Configuration System**
```python
@dataclass
class ValidationConfig:
    """Configuration for validation framework."""

    row_drift_tolerance: float = 0.005
    require_pk_uniqueness: bool = True
    max_hire_termination_ratio: float = 3.0
    min_hire_termination_ratio: float = 0.3
    enable_anomaly_detection: bool = True
    anomaly_z_score_threshold: float = 3.0

def setup_default_validators(config: ValidationConfig) -> DataValidator:
    """Setup validator with default rules based on configuration."""
    validator = DataValidator()

    # Add standard validation rules
    validator.register_rule(RowCountDriftRule(config.row_drift_tolerance))
    validator.register_rule(HireTerminationRatioRule(
        config.max_hire_termination_ratio,
        config.min_hire_termination_ratio
    ))
    validator.register_rule(EventSequenceRule())

    if config.require_pk_uniqueness:
        validator.register_rule(PrimaryKeyUniquenessRule())

    return validator
```

---

**This story provides comprehensive data quality assurance with configurable rules, clear error reporting, and automated anomaly detection to ensure simulation reliability.**
