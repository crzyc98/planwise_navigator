# Story S079: HCE Determination Engine

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 8
**Priority**: Medium

## Story

**As a** plan administrator
**I want** accurate HCE determination for partial-year employees
**So that** ACP/ADP testing and plan compliance are correctly calculated

## Business Context

This story implements the Highly Compensated Employee (HCE) determination engine, which is critical for 401(k) plan compliance testing. The engine handles complex scenarios including partial-year employees, mid-year HCE status changes, and multiple determination methods while ensuring accurate compensation annualization.

## Acceptance Criteria

### Core HCE Determination Features
- [ ] **Real-time HCE status calculation** using YTD compensation
- [ ] **Integration with plan-year-specific IRS HCE thresholds**
- [ ] **Support for prior-year and current-year determination methods**
- [ ] **Partial-year employee compensation annualization** logic
- [ ] **HCE status change events** when threshold crossed mid-year
- [ ] **Lookback period support** for prior-year determination

### Testing Coverage Requirements
- [ ] **Unit tests covering**:
  - New hires starting mid-year
  - Terminations with partial-year compensation
  - Employees crossing HCE threshold mid-year
  - Multi-year HCE status transitions

## Technical Specifications

### HCE Determination Models
```python
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

class HCEDeterminationMethod(str, Enum):
    PRIOR_YEAR = "prior_year"
    CURRENT_YEAR = "current_year"
    CALENDAR_YEAR = "calendar_year"

class CompensationPeriod(BaseModel):
    start_date: date
    end_date: date
    compensation_amount: Decimal
    pay_periods: int
    is_complete_year: bool

class HCECalculationInput(BaseModel):
    employee_id: str
    plan_id: str
    plan_year: int
    determination_method: HCEDeterminationMethod
    hire_date: date
    termination_date: Optional[date] = None
    birth_date: date

    # Compensation data
    current_year_compensation: List[CompensationPeriod]
    prior_year_compensation: Optional[List[CompensationPeriod]] = None

    # HCE threshold
    hce_threshold: Decimal

    # Additional context
    calculation_date: date = Field(default_factory=date.today)
    include_bonuses: bool = True
    include_overtime: bool = True

class HCEDeterminationResult(BaseModel):
    employee_id: str
    plan_id: str
    plan_year: int
    calculation_date: date

    # Determination details
    determination_method: HCEDeterminationMethod
    compensation_used: Decimal
    annualized_compensation: Decimal
    hce_threshold: Decimal

    # Results
    is_hce: bool
    hce_status_changed: bool

    # Supporting data
    years_of_service: float
    employment_status: str
    partial_year_employee: bool
    annualization_factor: Optional[float] = None

    # Historical context
    prior_year_hce: Optional[bool] = None

    # Audit trail
    calculation_details: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)

class HCEStatusChangeEvent(BaseModel):
    employee_id: str
    plan_id: str
    effective_date: date
    plan_year: int

    # Change details
    previous_hce_status: bool
    new_hce_status: bool
    trigger_compensation: Decimal
    hce_threshold: Decimal

    # Context
    determination_method: HCEDeterminationMethod
    change_reason: str  # 'threshold_crossed', 'new_hire', 'method_change'
    notification_required: bool = True
```

### HCE Calculation Engine
```python
class HCEDeterminationEngine:
    """Engine for calculating HCE status with complex business rules"""

    def __init__(self, irs_limits_service, compensation_service):
        self.irs_limits_service = irs_limits_service
        self.compensation_service = compensation_service

    def calculate_hce_status(self, input_data: HCECalculationInput) -> HCEDeterminationResult:
        """Calculate HCE status using specified determination method"""

        # Get compensation data based on determination method
        if input_data.determination_method == HCEDeterminationMethod.PRIOR_YEAR:
            compensation_periods = input_data.prior_year_compensation or []
            compensation_year = input_data.plan_year - 1
        else:
            compensation_periods = input_data.current_year_compensation
            compensation_year = input_data.plan_year

        # Calculate total and annualized compensation
        compensation_result = self._calculate_compensation(
            compensation_periods=compensation_periods,
            hire_date=input_data.hire_date,
            termination_date=input_data.termination_date,
            calculation_date=input_data.calculation_date,
            compensation_year=compensation_year
        )

        # Determine HCE status
        is_hce = compensation_result['annualized_compensation'] >= input_data.hce_threshold

        # Check for status change
        hce_status_changed = self._check_status_change(
            employee_id=input_data.employee_id,
            plan_year=input_data.plan_year,
            new_hce_status=is_hce
        )

        # Build result
        result = HCEDeterminationResult(
            employee_id=input_data.employee_id,
            plan_id=input_data.plan_id,
            plan_year=input_data.plan_year,
            calculation_date=input_data.calculation_date,
            determination_method=input_data.determination_method,
            compensation_used=compensation_result['total_compensation'],
            annualized_compensation=compensation_result['annualized_compensation'],
            hce_threshold=input_data.hce_threshold,
            is_hce=is_hce,
            hce_status_changed=hce_status_changed,
            partial_year_employee=compensation_result['is_partial_year'],
            annualization_factor=compensation_result.get('annualization_factor'),
            calculation_details=compensation_result['details']
        )

        return result

    def _calculate_compensation(
        self,
        compensation_periods: List[CompensationPeriod],
        hire_date: date,
        termination_date: Optional[date],
        calculation_date: date,
        compensation_year: int
    ) -> Dict[str, Any]:
        """Calculate total and annualized compensation"""

        if not compensation_periods:
            return {
                'total_compensation': Decimal('0'),
                'annualized_compensation': Decimal('0'),
                'is_partial_year': True,
                'annualization_factor': 0,
                'details': {'reason': 'no_compensation_data'}
            }

        # Calculate total compensation
        total_compensation = sum(period.compensation_amount for period in compensation_periods)

        # Determine if this is a partial year employee
        year_start = date(compensation_year, 1, 1)
        year_end = date(compensation_year, 12, 31)

        # Employee's active period during the compensation year
        active_start = max(hire_date, year_start)
        active_end = min(termination_date or calculation_date, year_end)

        # Check if employee worked full year
        is_full_year = (active_start <= year_start and active_end >= year_end)

        if is_full_year:
            # Full year employee - no annualization needed
            annualized_compensation = total_compensation
            annualization_factor = 1.0
        else:
            # Partial year employee - annualize compensation
            days_worked = (active_end - active_start).days + 1
            days_in_year = 365  # Standard assumption for annualization

            if days_worked <= 0:
                annualization_factor = 0
                annualized_compensation = Decimal('0')
            else:
                annualization_factor = days_in_year / days_worked
                annualized_compensation = total_compensation * Decimal(str(annualization_factor))

        return {
            'total_compensation': total_compensation,
            'annualized_compensation': annualized_compensation,
            'is_partial_year': not is_full_year,
            'annualization_factor': annualization_factor,
            'details': {
                'compensation_periods': len(compensation_periods),
                'active_start': active_start,
                'active_end': active_end,
                'days_worked': (active_end - active_start).days + 1,
                'annualization_method': 'calendar_days'
            }
        }

    def _check_status_change(
        self,
        employee_id: str,
        plan_year: int,
        new_hce_status: bool
    ) -> bool:
        """Check if HCE status has changed from previous determination"""
        # This would query previous HCE determination
        # For demonstration, returning False
        return False

    def calculate_batch_hce_status(
        self,
        employee_ids: List[str],
        plan_id: str,
        plan_year: int,
        determination_method: HCEDeterminationMethod,
        calculation_date: Optional[date] = None
    ) -> List[HCEDeterminationResult]:
        """Calculate HCE status for multiple employees efficiently"""

        calculation_date = calculation_date or date.today()
        results = []

        # Get IRS threshold for the year
        irs_limits = self.irs_limits_service.get_limits(plan_year)
        hce_threshold = irs_limits.hce_threshold

        # Batch load employee data
        employee_data = self.compensation_service.get_batch_employee_data(
            employee_ids=employee_ids,
            plan_year=plan_year,
            determination_method=determination_method
        )

        for employee_id in employee_ids:
            emp_data = employee_data.get(employee_id)
            if not emp_data:
                continue

            # Build calculation input
            calc_input = HCECalculationInput(
                employee_id=employee_id,
                plan_id=plan_id,
                plan_year=plan_year,
                determination_method=determination_method,
                hire_date=emp_data['hire_date'],
                termination_date=emp_data.get('termination_date'),
                birth_date=emp_data['birth_date'],
                current_year_compensation=emp_data['current_year_compensation'],
                prior_year_compensation=emp_data.get('prior_year_compensation'),
                hce_threshold=hce_threshold,
                calculation_date=calculation_date
            )

            # Calculate HCE status
            result = self.calculate_hce_status(calc_input)
            results.append(result)

        return results

    def trigger_mid_year_recalculation(
        self,
        employee_id: str,
        plan_id: str,
        compensation_event: Dict[str, Any]
    ) -> Optional[HCEStatusChangeEvent]:
        """Trigger HCE recalculation when compensation changes mid-year"""

        effective_date = compensation_event['effective_date']
        plan_year = effective_date.year

        # Get current HCE threshold
        irs_limits = self.irs_limits_service.get_limits(plan_year)

        # Get updated YTD compensation
        ytd_compensation = self.compensation_service.get_ytd_compensation(
            employee_id=employee_id,
            as_of_date=effective_date
        )

        # Get employee data for annualization
        employee_data = self.compensation_service.get_employee_data(employee_id)

        # Calculate annualized compensation
        hire_date = employee_data['hire_date']
        if hire_date.year == plan_year:
            # New hire - annualize based on hire date
            months_worked = (effective_date.month - hire_date.month) + 1
            annualized_compensation = ytd_compensation * Decimal('12') / Decimal(str(months_worked))
        else:
            # Existing employee - project based on YTD
            days_into_year = (effective_date - date(plan_year, 1, 1)).days + 1
            days_in_year = 365
            annualized_compensation = ytd_compensation * Decimal(str(days_in_year)) / Decimal(str(days_into_year))

        # Determine new HCE status
        new_hce_status = annualized_compensation >= irs_limits.hce_threshold

        # Get previous HCE status
        previous_hce_status = self._get_current_hce_status(employee_id, plan_year)

        # Check if status changed
        if new_hce_status != previous_hce_status:
            return HCEStatusChangeEvent(
                employee_id=employee_id,
                plan_id=plan_id,
                effective_date=effective_date,
                plan_year=plan_year,
                previous_hce_status=previous_hce_status,
                new_hce_status=new_hce_status,
                trigger_compensation=annualized_compensation,
                hce_threshold=irs_limits.hce_threshold,
                determination_method=HCEDeterminationMethod.CURRENT_YEAR,
                change_reason='compensation_change'
            )

        return None

    def _get_current_hce_status(self, employee_id: str, plan_year: int) -> bool:
        """Get current HCE status for employee"""
        # This would query the current HCE status from storage
        # For demonstration, returning False
        return False
```

### Compensation Service Integration
```python
class CompensationService:
    """Service for retrieving and processing compensation data"""

    def __init__(self, db_connection):
        self.db = db_connection

    def get_ytd_compensation(
        self,
        employee_id: str,
        as_of_date: date,
        include_bonuses: bool = True,
        include_overtime: bool = True
    ) -> Decimal:
        """Get year-to-date compensation as of specific date"""

        year_start = date(as_of_date.year, 1, 1)

        query = """
            SELECT SUM(compensation_amount) as ytd_compensation
            FROM fct_compensation_events
            WHERE employee_id = ?
                AND effective_date BETWEEN ? AND ?
                AND compensation_type IN ('base_salary', 'wages')
        """

        params = [employee_id, year_start, as_of_date]

        # Add bonus and overtime if included
        if include_bonuses:
            query = query.replace("('base_salary', 'wages')", "('base_salary', 'wages', 'bonus')")

        if include_overtime:
            query = query.replace("('base_salary', 'wages')", "('base_salary', 'wages', 'overtime')")

        result = self.db.execute(query, params).fetchone()
        return Decimal(str(result['ytd_compensation'] or 0))

    def get_annual_compensation(
        self,
        employee_id: str,
        year: int
    ) -> List[CompensationPeriod]:
        """Get all compensation periods for a specific year"""

        query = """
            SELECT
                DATE_TRUNC('month', effective_date) as period_start,
                LAST_DAY(effective_date) as period_end,
                SUM(compensation_amount) as period_compensation,
                COUNT(*) as pay_periods
            FROM fct_compensation_events
            WHERE employee_id = ?
                AND YEAR(effective_date) = ?
            GROUP BY DATE_TRUNC('month', effective_date)
            ORDER BY period_start
        """

        results = self.db.execute(query, [employee_id, year]).fetchall()

        compensation_periods = []
        for row in results:
            period = CompensationPeriod(
                start_date=row['period_start'],
                end_date=row['period_end'],
                compensation_amount=Decimal(str(row['period_compensation'])),
                pay_periods=row['pay_periods'],
                is_complete_year=(row['period_start'].month == 1 and
                                row['period_end'].month == 12)
            )
            compensation_periods.append(period)

        return compensation_periods

    def get_batch_employee_data(
        self,
        employee_ids: List[str],
        plan_year: int,
        determination_method: HCEDeterminationMethod
    ) -> Dict[str, Dict[str, Any]]:
        """Get compensation data for multiple employees efficiently"""

        employee_data = {}

        # Get basic employee information
        emp_query = """
            SELECT
                employee_id,
                hire_date,
                termination_date,
                birth_date
            FROM int_employee_demographics
            WHERE employee_id IN ({})
        """.format(','.join('?' * len(employee_ids)))

        emp_results = self.db.execute(emp_query, employee_ids).fetchall()

        for row in emp_results:
            employee_id = row['employee_id']
            employee_data[employee_id] = {
                'hire_date': row['hire_date'],
                'termination_date': row['termination_date'],
                'birth_date': row['birth_date'],
                'current_year_compensation': self.get_annual_compensation(employee_id, plan_year),
                'prior_year_compensation': self.get_annual_compensation(employee_id, plan_year - 1)
                    if determination_method == HCEDeterminationMethod.PRIOR_YEAR else None
            }

        return employee_data
```

### dbt Models for HCE Determination
```sql
-- int_hce_determination.sql
{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'plan_year', 'determination_method'],
    on_schema_change='fail',
    contract={'enforced': true},
    tags=['intermediate', 'dc_plan', 'hce'],
    indexes=[
        {'columns': ['employee_id', 'plan_year'], 'type': 'hash'},
        {'columns': ['is_hce'], 'type': 'btree'}
    ]
) }}

WITH employee_compensation AS (
    SELECT
        e.employee_id,
        e.plan_year,
        e.hire_date,
        e.termination_date,
        e.birth_date,
        -- Current year compensation
        SUM(CASE WHEN ce.plan_year = e.plan_year THEN ce.compensation_amount ELSE 0 END) as current_year_compensation,
        COUNT(CASE WHEN ce.plan_year = e.plan_year THEN 1 END) as current_year_pay_periods,
        -- Prior year compensation
        SUM(CASE WHEN ce.plan_year = e.plan_year - 1 THEN ce.compensation_amount ELSE 0 END) as prior_year_compensation,
        COUNT(CASE WHEN ce.plan_year = e.plan_year - 1 THEN 1 END) as prior_year_pay_periods
    FROM {{ ref('int_employee_demographics') }} e
    LEFT JOIN {{ ref('fct_compensation_events') }} ce
        ON e.employee_id = ce.employee_id
        AND ce.plan_year IN (e.plan_year, e.plan_year - 1)
    GROUP BY e.employee_id, e.plan_year, e.hire_date, e.termination_date, e.birth_date
),
compensation_annualization AS (
    SELECT
        *,
        -- Determine if partial year employee
        CASE
            WHEN hire_date >= DATE_TRUNC('year', DATE(plan_year || '-01-01'))
                OR termination_date <= DATE_TRUNC('year', DATE(plan_year || '-12-31'))
            THEN TRUE
            ELSE FALSE
        END as is_partial_year_current,

        -- Calculate annualized compensation for current year
        CASE
            WHEN hire_date >= DATE_TRUNC('year', DATE(plan_year || '-01-01')) THEN
                -- New hire - annualize based on months worked
                current_year_compensation * 12.0 / GREATEST(1, current_year_pay_periods)
            WHEN termination_date <= DATE_TRUNC('year', DATE(plan_year || '-12-31')) THEN
                -- Termination - annualize based on months worked
                current_year_compensation * 12.0 / GREATEST(1, current_year_pay_periods)
            ELSE
                -- Full year employee
                current_year_compensation
        END as annualized_current_compensation,

        -- Prior year is always used as-is (no annualization for prior year method)
        prior_year_compensation as annualized_prior_compensation
    FROM employee_compensation
),
hce_thresholds AS (
    SELECT
        plan_year,
        highly_compensated_threshold as hce_threshold
    FROM {{ ref('int_effective_irs_limits') }}
),
hce_determination AS (
    SELECT
        ca.employee_id,
        ca.plan_year,
        ca.hire_date,
        ca.termination_date,
        ca.current_year_compensation,
        ca.prior_year_compensation,
        ca.annualized_current_compensation,
        ca.annualized_prior_compensation,
        ca.is_partial_year_current,
        ht.hce_threshold,

        -- Current year determination
        ca.annualized_current_compensation >= ht.hce_threshold as is_hce_current_year,

        -- Prior year determination
        ca.prior_year_compensation >= LAG(ht.hce_threshold) OVER (
            PARTITION BY ca.employee_id ORDER BY ca.plan_year
        ) as is_hce_prior_year,

        -- Default determination method (current year)
        'current_year' as determination_method,

        CURRENT_TIMESTAMP as calculated_at
    FROM compensation_annualization ca
    JOIN hce_thresholds ht ON ca.plan_year = ht.plan_year
),
hce_status_changes AS (
    SELECT
        *,
        -- Track HCE status changes
        LAG(is_hce_current_year) OVER (
            PARTITION BY employee_id ORDER BY plan_year
        ) as prior_hce_status,

        CASE
            WHEN LAG(is_hce_current_year) OVER (
                PARTITION BY employee_id ORDER BY plan_year
            ) != is_hce_current_year THEN TRUE
            ELSE FALSE
        END as hce_status_changed
    FROM hce_determination
)
SELECT
    employee_id,
    plan_year,
    determination_method,
    current_year_compensation,
    prior_year_compensation,
    annualized_current_compensation,
    hce_threshold,
    is_hce_current_year as is_hce,
    is_partial_year_current as is_partial_year,
    hce_status_changed,
    prior_hce_status,
    calculated_at
FROM hce_status_changes
{% if is_incremental() %}
    WHERE calculated_at > (SELECT MAX(calculated_at) FROM {{ this }})
{% endif %}
```

## Implementation Tasks

### Phase 1: Core HCE Engine
- [ ] **Implement HCE determination models** with Pydantic validation
- [ ] **Create HCE calculation engine** with annualization logic
- [ ] **Build compensation service integration** for data retrieval
- [ ] **Add comprehensive unit tests** for all calculation scenarios

### Phase 2: Advanced Features
- [ ] **Implement mid-year recalculation** triggers
- [ ] **Create HCE status change tracking** and event generation
- [ ] **Build batch processing** for efficient bulk calculations
- [ ] **Add integration with IRS limits service**

### Phase 3: dbt Integration
- [ ] **Create dbt models** for HCE determination
- [ ] **Implement incremental processing** for performance
- [ ] **Build HCE status change tracking** in data warehouse
- [ ] **Add comprehensive testing** including edge cases

## Dependencies

- **S072**: Event Schema (for HCE status events)
- **S081**: Regulatory Limits Service (for HCE thresholds)
- **Compensation events**: Source data for calculations
- **Employee demographics**: Hire dates, termination dates
- **IRS limits data**: Annual HCE thresholds

## Success Metrics

### Accuracy Requirements
- [ ] **Calculation accuracy**: 100% match with manual calculations
- [ ] **Annualization logic**: Correct for all partial-year scenarios
- [ ] **Status change detection**: Real-time identification of threshold crossings
- [ ] **Multi-year consistency**: Proper handling of determination method changes

### Performance Requirements
- [ ] **Single calculation**: <50ms per employee
- [ ] **Batch processing**: 10,000 employees in <2 minutes
- [ ] **Mid-year recalculation**: <100ms trigger response
- [ ] **Memory efficiency**: <200MB for 100K employee calculations

## Definition of Done

- [ ] **Complete HCE determination engine** supporting all calculation methods
- [ ] **Partial-year employee handling** with accurate annualization
- [ ] **Mid-year recalculation triggers** for compensation changes
- [ ] **HCE status change tracking** with event generation
- [ ] **dbt models** for data warehouse integration
- [ ] **Comprehensive testing** covering all edge cases
- [ ] **Performance benchmarks met** for enterprise scale
- [ ] **Documentation complete** with calculation examples and regulatory references
