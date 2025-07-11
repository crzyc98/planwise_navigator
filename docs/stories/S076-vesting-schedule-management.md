# Story S076: Vesting Schedule Management

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 5
**Priority**: Medium

## Story

**As a** plan administrator
**I want** comprehensive vesting calculation and forfeiture tracking
**So that** terminated employees forfeit non-vested amounts correctly

## Business Context

This story implements vesting schedule management and forfeiture processing for retirement plan accounts. It ensures accurate calculation of vested percentages based on service computation dates and automatically processes forfeitures when participants terminate employment with non-vested balances.

## Acceptance Criteria

### Core Vesting Features
- [ ] **Event types for vesting calculations and forfeitures**
- [ ] **Support for graded, cliff, and immediate vesting schedules**
- [ ] **Integration with termination events** from workforce simulation
- [ ] **Automated forfeiture processing** for non-vested amounts
- [ ] **Service computation date tracking** for eligibility calculations

### Vesting Calculation Requirements
- [ ] **Accurate service computation** based on hire date or plan entry date
- [ ] **Break-in-service rules** for rehired employees
- [ ] **Years of service calculation** including partial years
- [ ] **Multiple vesting schedules** per plan (e.g., different for match vs. profit sharing)
- [ ] **Retroactive vesting updates** when schedule changes

## Technical Specifications

### Vesting Schedule Models
```python
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, validator
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

class VestingType(str, Enum):
    IMMEDIATE = "immediate"
    CLIFF = "cliff"
    GRADED = "graded"
    CUSTOM = "custom"

class ServiceComputationMethod(str, Enum):
    HIRE_DATE = "hire_date"
    PLAN_ENTRY_DATE = "plan_entry_date"
    CUSTOM_DATE = "custom_date"

class VestingSchedulePoint(BaseModel):
    years_of_service: float = Field(..., ge=0, le=50)
    vested_percentage: float = Field(..., ge=0, le=1)

    @validator('vested_percentage')
    def validate_percentage(cls, v):
        # Round to 4 decimal places to avoid floating point issues
        return round(v, 4)

class VestingSchedule(BaseModel):
    schedule_id: str
    schedule_name: str
    vesting_type: VestingType
    service_computation_method: ServiceComputationMethod
    schedule_points: List[VestingSchedulePoint]
    applies_to_sources: List[str]  # Which contribution sources use this schedule
    break_in_service_rule: Optional[str] = "5_year_rule"

    @validator('schedule_points')
    def validate_schedule_points(cls, v, values):
        vesting_type = values.get('vesting_type')

        if vesting_type == VestingType.IMMEDIATE:
            # Immediate vesting should have single 0-year 100% point
            if len(v) != 1 or v[0].years_of_service != 0 or v[0].vested_percentage != 1.0:
                raise ValueError("Immediate vesting must have single point at 0 years with 100%")

        elif vesting_type == VestingType.CLIFF:
            # Cliff vesting should have exactly 2 points: 0% and 100%
            if len(v) != 2:
                raise ValueError("Cliff vesting must have exactly 2 points")
            if v[0].vested_percentage != 0 or v[1].vested_percentage != 1.0:
                raise ValueError("Cliff vesting must go from 0% to 100%")

        elif vesting_type == VestingType.GRADED:
            # Graded vesting should have increasing percentages
            for i in range(1, len(v)):
                if v[i].years_of_service <= v[i-1].years_of_service:
                    raise ValueError("Years of service must be increasing")
                if v[i].vested_percentage <= v[i-1].vested_percentage:
                    raise ValueError("Vested percentages must be increasing")
            # Last point should be 100%
            if v[-1].vested_percentage != 1.0:
                raise ValueError("Final vesting percentage must be 100%")

        return v

class ServiceCalculation(BaseModel):
    employee_id: str
    calculation_date: date
    hire_date: date
    termination_date: Optional[date] = None
    plan_entry_date: Optional[date] = None
    service_computation_date: date
    break_in_service_periods: List[Dict[str, date]] = Field(default_factory=list)

    def calculate_years_of_service(self) -> float:
        """Calculate years of service accounting for breaks"""
        # Start from service computation date
        start_date = self.service_computation_date
        end_date = self.termination_date or self.calculation_date

        # Calculate total service period
        total_days = (end_date - start_date).days

        # Subtract break-in-service periods
        break_days = 0
        for break_period in self.break_in_service_periods:
            break_start = break_period['start_date']
            break_end = break_period['end_date']

            # Only count breaks within the service period
            if break_end >= start_date and break_start <= end_date:
                effective_break_start = max(break_start, start_date)
                effective_break_end = min(break_end, end_date)
                break_days += (effective_break_end - effective_break_start).days

        # Calculate years of service (using 365.25 for leap years)
        service_days = total_days - break_days
        years_of_service = service_days / 365.25

        return round(years_of_service, 4)
```

### Vesting Calculation Engine
```python
class VestingCalculationEngine:
    """Calculates vested percentages based on vesting schedules"""

    def __init__(self, vesting_schedules: Dict[str, VestingSchedule]):
        self.vesting_schedules = vesting_schedules

    def calculate_vested_percentage(
        self,
        schedule_id: str,
        years_of_service: float
    ) -> float:
        """Calculate vested percentage for given years of service"""
        schedule = self.vesting_schedules.get(schedule_id)
        if not schedule:
            raise ValueError(f"Unknown vesting schedule: {schedule_id}")

        # Handle immediate vesting
        if schedule.vesting_type == VestingType.IMMEDIATE:
            return 1.0

        # Find applicable vesting point
        schedule_points = sorted(schedule.schedule_points, key=lambda x: x.years_of_service)

        # If service is less than first point, return that percentage (usually 0)
        if years_of_service < schedule_points[0].years_of_service:
            return schedule_points[0].vested_percentage

        # If service exceeds last point, return 100%
        if years_of_service >= schedule_points[-1].years_of_service:
            return schedule_points[-1].vested_percentage

        # Find the applicable range and interpolate if graded
        for i in range(len(schedule_points) - 1):
            current_point = schedule_points[i]
            next_point = schedule_points[i + 1]

            if current_point.years_of_service <= years_of_service < next_point.years_of_service:
                if schedule.vesting_type == VestingType.CLIFF:
                    # For cliff vesting, use the current point's percentage
                    return current_point.vested_percentage
                else:
                    # For graded vesting, interpolate between points
                    years_range = next_point.years_of_service - current_point.years_of_service
                    pct_range = next_point.vested_percentage - current_point.vested_percentage
                    years_into_range = years_of_service - current_point.years_of_service

                    interpolated_pct = current_point.vested_percentage + (years_into_range / years_range) * pct_range
                    return round(interpolated_pct, 4)

        return schedule_points[-1].vested_percentage

    def calculate_account_vesting(
        self,
        employee_id: str,
        account_balances: Dict[str, Decimal],
        years_of_service: float,
        plan_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate vested amounts for all contribution sources"""
        vesting_results = {
            'employee_id': employee_id,
            'years_of_service': years_of_service,
            'source_vesting': {},
            'total_balance': Decimal('0'),
            'vested_balance': Decimal('0'),
            'unvested_balance': Decimal('0')
        }

        for source, balance in account_balances.items():
            # Employee contributions are always 100% vested
            if source.startswith('employee_'):
                vested_pct = 1.0
            else:
                # Find applicable vesting schedule for this source
                schedule_id = self._find_schedule_for_source(source, plan_config)
                vested_pct = self.calculate_vested_percentage(schedule_id, years_of_service)

            vested_amount = balance * Decimal(str(vested_pct))
            unvested_amount = balance - vested_amount

            vesting_results['source_vesting'][source] = {
                'balance': balance,
                'vested_percentage': vested_pct,
                'vested_amount': vested_amount,
                'unvested_amount': unvested_amount
            }

            vesting_results['total_balance'] += balance
            vesting_results['vested_balance'] += vested_amount
            vesting_results['unvested_balance'] += unvested_amount

        return vesting_results

    def _find_schedule_for_source(self, source: str, plan_config: Dict[str, Any]) -> str:
        """Find the vesting schedule that applies to a contribution source"""
        # Logic to map contribution sources to vesting schedules
        vesting_config = plan_config.get('vesting_schedules', {})
        for schedule_id, schedule in vesting_config.items():
            if source in schedule.get('applies_to_sources', []):
                return schedule_id

        # Default schedule if no specific mapping found
        return plan_config.get('default_vesting_schedule', 'standard_graded')
```

### Forfeiture Processing
```python
class ForfeitureProcessor:
    """Processes forfeitures upon termination"""

    def __init__(self, vesting_engine: VestingCalculationEngine):
        self.vesting_engine = vesting_engine

    def process_termination_forfeiture(
        self,
        termination_event: Dict[str, Any],
        account_balances: Dict[str, Decimal],
        service_calculation: ServiceCalculation,
        plan_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process forfeitures for terminated employee"""
        employee_id = termination_event['employee_id']
        termination_date = termination_event['effective_date']

        # Calculate years of service as of termination
        years_of_service = service_calculation.calculate_years_of_service()

        # Calculate vesting for all sources
        vesting_results = self.vesting_engine.calculate_account_vesting(
            employee_id=employee_id,
            account_balances=account_balances,
            years_of_service=years_of_service,
            plan_config=plan_config
        )

        # Generate forfeiture events for unvested amounts
        forfeiture_events = []

        for source, vesting_detail in vesting_results['source_vesting'].items():
            unvested_amount = vesting_detail['unvested_amount']

            if unvested_amount > 0:
                forfeiture_event = {
                    'event_id': self._generate_event_id(),
                    'employee_id': employee_id,
                    'event_type': 'forfeiture',
                    'effective_date': termination_date,
                    'plan_year': termination_date.year,
                    'payload': {
                        'forfeiture_reason': 'termination_unvested',
                        'contribution_source': source,
                        'forfeited_amount': float(unvested_amount),
                        'vested_percentage': vesting_detail['vested_percentage'],
                        'years_of_service': years_of_service,
                        'original_balance': float(vesting_detail['balance'])
                    },
                    'created_at': datetime.utcnow(),
                    'source_system': 'vesting_engine'
                }
                forfeiture_events.append(forfeiture_event)

        # Create forfeiture allocation event for plan use
        if vesting_results['unvested_balance'] > 0:
            allocation_event = {
                'event_id': self._generate_event_id(),
                'employee_id': 'PLAN',  # Forfeitures go to plan level
                'event_type': 'forfeiture_allocation',
                'effective_date': termination_date,
                'plan_year': termination_date.year,
                'payload': {
                    'allocation_method': plan_config.get('forfeiture_allocation_method', 'reduce_contributions'),
                    'total_forfeited': float(vesting_results['unvested_balance']),
                    'from_employee_id': employee_id,
                    'allocation_timing': plan_config.get('forfeiture_allocation_timing', 'plan_year_end')
                },
                'created_at': datetime.utcnow(),
                'source_system': 'vesting_engine'
            }
            forfeiture_events.append(allocation_event)

        return {
            'employee_id': employee_id,
            'termination_date': termination_date,
            'vesting_results': vesting_results,
            'forfeiture_events': forfeiture_events,
            'total_forfeited': float(vesting_results['unvested_balance'])
        }

    def _generate_event_id(self) -> str:
        """Generate unique event ID"""
        import uuid
        return str(uuid.uuid4())
```

### Rehire and Break-in-Service Handling
```python
class RehireVestingManager:
    """Manages vesting for rehired employees"""

    def calculate_rehire_vesting(
        self,
        employee_id: str,
        original_hire_date: date,
        termination_date: date,
        rehire_date: date,
        prior_vesting_percentage: float,
        prior_years_of_service: float,
        plan_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate vesting credit for rehired employee"""

        # Calculate break in service
        break_duration = (rehire_date - termination_date).days / 365.25

        # Apply break-in-service rules
        break_in_service_threshold = plan_config.get('break_in_service_years', 5)

        if break_duration >= break_in_service_threshold:
            # Lost prior service credit
            return {
                'service_credit_retained': False,
                'adjusted_years_of_service': 0,
                'adjusted_vesting_percentage': 0,
                'service_computation_date': rehire_date,
                'break_duration_years': break_duration
            }
        else:
            # Retain prior service credit
            return {
                'service_credit_retained': True,
                'adjusted_years_of_service': prior_years_of_service,
                'adjusted_vesting_percentage': prior_vesting_percentage,
                'service_computation_date': original_hire_date,
                'break_duration_years': break_duration
            }
```

### dbt Models for Vesting
```sql
-- int_vesting_calculation.sql
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['intermediate', 'dc_plan', 'vesting']
) }}

WITH employee_service AS (
    SELECT
        e.employee_id,
        e.hire_date,
        e.termination_date,
        e.plan_entry_date,
        COALESCE(e.service_computation_date, e.hire_date) as service_computation_date,
        -- Calculate years of service
        DATEDIFF('day',
            COALESCE(e.service_computation_date, e.hire_date),
            COALESCE(e.termination_date, CURRENT_DATE)
        ) / 365.25 as years_of_service
    FROM {{ ref('int_employee_demographics') }} e
),
vesting_schedules AS (
    SELECT
        vs.schedule_id,
        vs.vesting_type,
        vs.schedule_points,
        vs.applies_to_sources
    FROM {{ ref('plan_vesting_schedules') }} vs
    WHERE vs.effective_date <= CURRENT_DATE
),
calculated_vesting AS (
    SELECT
        es.employee_id,
        es.years_of_service,
        vs.schedule_id,
        vs.vesting_type,
        -- Calculate vested percentage based on schedule
        CASE
            WHEN vs.vesting_type = 'immediate' THEN 1.0
            WHEN vs.vesting_type = 'cliff' AND es.years_of_service >= 3 THEN 1.0
            WHEN vs.vesting_type = 'cliff' THEN 0.0
            WHEN vs.vesting_type = 'graded' THEN
                CASE
                    WHEN es.years_of_service < 2 THEN 0.0
                    WHEN es.years_of_service >= 6 THEN 1.0
                    ELSE LEAST(1.0, GREATEST(0.0, (es.years_of_service - 2) * 0.25))
                END
            ELSE 0.0
        END as vested_percentage
    FROM employee_service es
    CROSS JOIN vesting_schedules vs
)
SELECT
    cv.*,
    CURRENT_TIMESTAMP as calculation_timestamp
FROM calculated_vesting cv
```

## Implementation Tasks

### Phase 1: Core Vesting Logic
- [ ] **Implement vesting schedule models** with validation
- [ ] **Create vesting calculation engine** supporting all schedule types
- [ ] **Build service calculation logic** with break-in-service handling
- [ ] **Add comprehensive unit tests** for vesting calculations

### Phase 2: Forfeiture Processing
- [ ] **Implement forfeiture processor** for termination events
- [ ] **Create forfeiture allocation logic** based on plan rules
- [ ] **Build forfeiture event generation** for audit trail
- [ ] **Add integration with termination events** from workforce simulation

### Phase 3: Advanced Features
- [ ] **Implement rehire vesting logic** with service credit rules
- [ ] **Create dbt models** for vesting calculations
- [ ] **Build vesting change tracking** for schedule updates
- [ ] **Add retroactive vesting recalculation** capabilities

## Dependencies

- **S072**: Retirement Plan Event Schema (defines forfeiture events)
- **S074**: Plan Configuration Schema (provides vesting schedules)
- **Workforce termination events**: Triggers forfeiture processing
- **Account balance data**: Required for forfeiture calculations

## Success Metrics

### Accuracy Requirements
- [ ] **Vesting calculation accuracy**: 100% match with manual calculations
- [ ] **Service computation**: Correct to 0.01 years precision
- [ ] **Forfeiture processing**: Zero missed forfeitures on termination
- [ ] **Break-in-service rules**: Correctly applied per ERISA guidelines

### Performance Requirements
- [ ] **Vesting calculation**: <50ms per employee
- [ ] **Batch processing**: 10,000 employees in <1 minute
- [ ] **Forfeiture event generation**: Real-time on termination
- [ ] **Memory efficiency**: <100MB for 100K employee calculations

## Definition of Done

- [ ] **Complete vesting engine** supporting all schedule types
- [ ] **Forfeiture processing** integrated with termination events
- [ ] **Service calculation** with break-in-service rules
- [ ] **Rehire logic** preserving or forfeiting prior service
- [ ] **dbt models** for vesting calculations and reporting
- [ ] **Comprehensive testing** covering all vesting scenarios
- [ ] **Performance benchmarks met** for enterprise scale
- [ ] **Documentation complete** with calculation examples
