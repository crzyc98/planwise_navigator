# Story S078: Workforce Event Integration

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 5
**Priority**: Medium

## Story

**As a** compliance officer
**I want** seamless integration with workforce simulation events
**So that** vesting and eligibility respond to employment changes

## Business Context

This story creates seamless integration between workforce simulation events and DC plan processing, ensuring that employment changes (hires, terminations, promotions, compensation adjustments) automatically trigger appropriate plan actions like eligibility calculations, vesting updates, and forfeiture processing.

## Acceptance Criteria

### Core Integration Features
- [ ] **Automatic triggering of vesting calculations** on termination
- [ ] **Forfeiture events for non-vested amounts** upon termination
- [ ] **Leave of absence impact** on vesting service computations
- [ ] **Rehire eligibility and vesting restoration** logic
- [ ] **Cross-system event correlation** and audit trail

### Event Trigger Requirements
- [ ] **Real-time processing** of workforce events
- [ ] **Eligibility recalculation** on hire and status changes
- [ ] **Compensation event processing** for HCE determination
- [ ] **Service computation updates** for vesting calculations
- [ ] **Plan participation triggers** based on eligibility rules

## Technical Specifications

### Workforce Event Handlers
```python
from typing import Dict, List, Any, Optional
from datetime import date, datetime
from decimal import Decimal
from abc import ABC, abstractmethod

class WorkforceEventHandler(ABC):
    """Base class for handling workforce events in DC plan context"""

    def __init__(self, plan_service, vesting_service, eligibility_service):
        self.plan_service = plan_service
        self.vesting_service = vesting_service
        self.eligibility_service = eligibility_service

    @abstractmethod
    def handle_event(self, workforce_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process workforce event and return generated DC plan events"""
        pass

    @abstractmethod
    def get_supported_event_types(self) -> List[str]:
        """Return list of workforce event types this handler supports"""
        pass

class HireEventHandler(WorkforceEventHandler):
    """Handles new hire events for DC plan enrollment"""

    def handle_event(self, workforce_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process hire event and generate eligibility/enrollment events"""
        employee_id = workforce_event['employee_id']
        hire_date = workforce_event['effective_date']
        employee_data = workforce_event.get('employee_data', {})

        generated_events = []

        # Check plan eligibility
        eligibility_result = self.eligibility_service.evaluate_eligibility(
            employee_id=employee_id,
            hire_date=hire_date,
            employee_data=employee_data
        )

        if eligibility_result['is_eligible']:
            # Generate eligibility event
            eligibility_event = {
                'event_id': self._generate_event_id(),
                'employee_id': employee_id,
                'event_type': 'eligibility',
                'effective_date': eligibility_result['eligibility_date'],
                'plan_year': eligibility_result['eligibility_date'].year,
                'payload': {
                    'plan_id': eligibility_result['plan_id'],
                    'eligibility_reason': 'hire_criteria_met',
                    'minimum_age_met': eligibility_result['age_eligible'],
                    'service_requirement_met': eligibility_result['service_eligible'],
                    'hours_requirement_met': eligibility_result['hours_eligible'],
                    'entry_date': eligibility_result['entry_date'],
                    'auto_enrollment_applicable': eligibility_result.get('auto_enrollment', False)
                },
                'created_at': datetime.utcnow(),
                'source_system': 'workforce_integration',
                'correlation_id': workforce_event['event_id']
            }
            generated_events.append(eligibility_event)

            # Generate auto-enrollment if applicable
            if eligibility_result.get('auto_enrollment', False):
                auto_enroll_event = self._generate_auto_enrollment_event(
                    employee_id, eligibility_result, workforce_event
                )
                generated_events.append(auto_enroll_event)

        return generated_events

    def _generate_auto_enrollment_event(
        self,
        employee_id: str,
        eligibility_result: Dict[str, Any],
        workforce_event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate auto-enrollment event for eligible employee"""
        plan_config = self.plan_service.get_plan_config(eligibility_result['plan_id'])
        auto_enroll_config = plan_config.get('auto_enrollment', {})

        return {
            'event_id': self._generate_event_id(),
            'employee_id': employee_id,
            'event_type': 'enrollment',
            'effective_date': eligibility_result['entry_date'],
            'plan_year': eligibility_result['entry_date'].year,
            'payload': {
                'plan_id': eligibility_result['plan_id'],
                'enrollment_method': 'auto_enrollment',
                'pre_tax_contribution_rate': auto_enroll_config.get('default_deferral_rate', 0.03),
                'roth_contribution_rate': 0.0,
                'auto_enrollment': True,
                'opt_out_window_expires': eligibility_result['entry_date'] + timedelta(
                    days=auto_enroll_config.get('opt_out_window_days', 90)
                )
            },
            'created_at': datetime.utcnow(),
            'source_system': 'workforce_integration',
            'correlation_id': workforce_event['event_id']
        }

    def get_supported_event_types(self) -> List[str]:
        return ['hire']

    def _generate_event_id(self) -> str:
        import uuid
        return str(uuid.uuid4())

class TerminationEventHandler(WorkforceEventHandler):
    """Handles termination events for vesting and forfeiture processing"""

    def handle_event(self, workforce_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process termination event and generate vesting/forfeiture events"""
        employee_id = workforce_event['employee_id']
        termination_date = workforce_event['effective_date']
        termination_reason = workforce_event.get('termination_reason', 'voluntary')

        generated_events = []

        # Get employee's current plan participation
        participant_accounts = self.plan_service.get_participant_accounts(employee_id)

        for account in participant_accounts:
            plan_id = account['plan_id']

            # Calculate final vesting
            vesting_result = self.vesting_service.calculate_termination_vesting(
                employee_id=employee_id,
                plan_id=plan_id,
                termination_date=termination_date,
                termination_reason=termination_reason
            )

            # Generate vesting event
            vesting_event = {
                'event_id': self._generate_event_id(),
                'employee_id': employee_id,
                'event_type': 'vesting',
                'effective_date': termination_date,
                'plan_year': termination_date.year,
                'payload': {
                    'plan_id': plan_id,
                    'vesting_reason': 'termination',
                    'vested_percentage': vesting_result['vested_percentage'],
                    'years_of_service': vesting_result['years_of_service'],
                    'service_computation_date': vesting_result['service_computation_date'],
                    'vesting_schedule_applied': vesting_result['schedule_id'],
                    'termination_reason': termination_reason
                },
                'created_at': datetime.utcnow(),
                'source_system': 'workforce_integration',
                'correlation_id': workforce_event['event_id']
            }
            generated_events.append(vesting_event)

            # Generate forfeiture events for unvested amounts
            forfeiture_events = self._generate_forfeiture_events(
                employee_id, plan_id, termination_date, vesting_result, workforce_event
            )
            generated_events.extend(forfeiture_events)

        return generated_events

    def _generate_forfeiture_events(
        self,
        employee_id: str,
        plan_id: str,
        termination_date: date,
        vesting_result: Dict[str, Any],
        workforce_event: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate forfeiture events for unvested balances"""
        forfeiture_events = []

        for source, source_vesting in vesting_result.get('source_vesting', {}).items():
            unvested_amount = source_vesting.get('unvested_amount', 0)

            if unvested_amount > 0:
                forfeiture_event = {
                    'event_id': self._generate_event_id(),
                    'employee_id': employee_id,
                    'event_type': 'forfeiture',
                    'effective_date': termination_date,
                    'plan_year': termination_date.year,
                    'payload': {
                        'plan_id': plan_id,
                        'forfeiture_reason': 'termination_unvested',
                        'contribution_source': source,
                        'forfeited_amount': unvested_amount,
                        'vested_percentage': source_vesting['vested_percentage'],
                        'years_of_service': vesting_result['years_of_service'],
                        'original_balance': source_vesting['balance'],
                        'termination_reason': workforce_event.get('termination_reason')
                    },
                    'created_at': datetime.utcnow(),
                    'source_system': 'workforce_integration',
                    'correlation_id': workforce_event['event_id']
                }
                forfeiture_events.append(forfeiture_event)

        return forfeiture_events

    def get_supported_event_types(self) -> List[str]:
        return ['termination']

    def _generate_event_id(self) -> str:
        import uuid
        return str(uuid.uuid4())

class CompensationEventHandler(WorkforceEventHandler):
    """Handles compensation changes for HCE determination"""

    def handle_event(self, workforce_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process compensation event and update HCE status if needed"""
        employee_id = workforce_event['employee_id']
        effective_date = workforce_event['effective_date']
        plan_year = effective_date.year

        # Get current compensation data
        new_compensation = workforce_event.get('new_compensation')
        if not new_compensation:
            return []

        generated_events = []

        # Check if HCE status needs recalculation
        hce_result = self.eligibility_service.recalculate_hce_status(
            employee_id=employee_id,
            plan_year=plan_year,
            effective_date=effective_date
        )

        if hce_result['status_changed']:
            hce_event = {
                'event_id': self._generate_event_id(),
                'employee_id': employee_id,
                'event_type': 'hce_status',
                'effective_date': effective_date,
                'plan_year': plan_year,
                'payload': {
                    'plan_id': hce_result['plan_id'],
                    'determination_method': hce_result['determination_method'],
                    'ytd_compensation': hce_result['ytd_compensation'],
                    'annualized_compensation': hce_result['annualized_compensation'],
                    'hce_threshold': hce_result['hce_threshold'],
                    'is_hce': hce_result['is_hce'],
                    'determination_date': effective_date,
                    'prior_year_hce': hce_result.get('prior_year_hce'),
                    'change_reason': 'compensation_update'
                },
                'created_at': datetime.utcnow(),
                'source_system': 'workforce_integration',
                'correlation_id': workforce_event['event_id']
            }
            generated_events.append(hce_event)

        return generated_events

    def get_supported_event_types(self) -> List[str]:
        return ['merit', 'promotion', 'compensation_change']

    def _generate_event_id(self) -> str:
        import uuid
        return str(uuid.uuid4())

class LeaveOfAbsenceHandler(WorkforceEventHandler):
    """Handles leave of absence events affecting service computation"""

    def handle_event(self, workforce_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process leave of absence for service computation impact"""
        employee_id = workforce_event['employee_id']
        leave_start_date = workforce_event['effective_date']
        leave_end_date = workforce_event.get('expected_return_date')
        leave_type = workforce_event.get('leave_type', 'unpaid')

        # Determine if leave affects service computation
        affects_service = self._leave_affects_service(leave_type, workforce_event)

        if not affects_service:
            return []

        # Generate service adjustment event
        service_event = {
            'event_id': self._generate_event_id(),
            'employee_id': employee_id,
            'event_type': 'service_adjustment',
            'effective_date': leave_start_date,
            'plan_year': leave_start_date.year,
            'payload': {
                'adjustment_type': 'leave_of_absence',
                'leave_type': leave_type,
                'leave_start_date': leave_start_date,
                'leave_end_date': leave_end_date,
                'affects_vesting_service': affects_service,
                'affects_eligibility_service': affects_service,
                'reason': f'{leave_type}_leave_of_absence'
            },
            'created_at': datetime.utcnow(),
            'source_system': 'workforce_integration',
            'correlation_id': workforce_event['event_id']
        }

        return [service_event]

    def _leave_affects_service(self, leave_type: str, workforce_event: Dict[str, Any]) -> bool:
        """Determine if leave type affects service computation"""
        # Define rules for when leave affects service
        no_service_impact_leaves = ['paid_vacation', 'paid_sick', 'jury_duty']
        service_impact_leaves = ['unpaid_personal', 'unpaid_medical', 'military']

        if leave_type in no_service_impact_leaves:
            return False
        elif leave_type in service_impact_leaves:
            return True
        else:
            # Default to checking duration
            leave_duration_days = workforce_event.get('duration_days', 0)
            return leave_duration_days > 30  # More than 30 days affects service

    def get_supported_event_types(self) -> List[str]:
        return ['leave_start', 'leave_end']

    def _generate_event_id(self) -> str:
        import uuid
        return str(uuid.uuid4())
```

### Integration Event Router
```python
class WorkforceEventRouter:
    """Routes workforce events to appropriate DC plan handlers"""

    def __init__(self):
        self.handlers: List[WorkforceEventHandler] = []
        self.event_correlation = {}

    def register_handler(self, handler: WorkforceEventHandler):
        """Register an event handler"""
        self.handlers.append(handler)

    def process_workforce_event(self, workforce_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process workforce event through all applicable handlers"""
        event_type = workforce_event.get('event_type')
        all_generated_events = []

        for handler in self.handlers:
            if event_type in handler.get_supported_event_types():
                try:
                    generated_events = handler.handle_event(workforce_event)
                    all_generated_events.extend(generated_events)

                    # Track correlation
                    self._track_event_correlation(workforce_event, generated_events)

                except Exception as e:
                    # Log error but continue processing
                    print(f"Error in handler {handler.__class__.__name__}: {e}")

        return all_generated_events

    def _track_event_correlation(
        self,
        workforce_event: Dict[str, Any],
        generated_events: List[Dict[str, Any]]
    ):
        """Track correlation between workforce and DC plan events"""
        workforce_event_id = workforce_event['event_id']
        generated_event_ids = [e['event_id'] for e in generated_events]

        self.event_correlation[workforce_event_id] = {
            'workforce_event': workforce_event,
            'generated_dc_events': generated_event_ids,
            'processed_at': datetime.utcnow()
        }
```

### Workforce Event Monitor
```python
class WorkforceEventMonitor:
    """Monitors workforce events and triggers DC plan processing"""

    def __init__(self, event_router, event_store, notification_service):
        self.router = event_router
        self.event_store = event_store
        self.notification_service = notification_service
        self.processing_queue = []

    def start_monitoring(self):
        """Start monitoring workforce events"""
        # This would typically listen to workforce event stream
        # For demonstration, showing the processing pattern
        pass

    def handle_workforce_event(self, workforce_event: Dict[str, Any]):
        """Handle incoming workforce event"""
        try:
            # Process event through router
            generated_events = self.router.process_workforce_event(workforce_event)

            # Store generated events
            for event in generated_events:
                self.event_store.save_event(event)

            # Send notifications if configured
            if generated_events:
                self._send_processing_notification(workforce_event, generated_events)

            # Update processing metrics
            self._update_metrics(workforce_event, generated_events)

        except Exception as e:
            # Handle processing errors
            self._handle_processing_error(workforce_event, e)

    def _send_processing_notification(
        self,
        workforce_event: Dict[str, Any],
        generated_events: List[Dict[str, Any]]
    ):
        """Send notification about event processing"""
        notification = {
            'type': 'workforce_event_processed',
            'workforce_event_id': workforce_event['event_id'],
            'employee_id': workforce_event['employee_id'],
            'event_type': workforce_event['event_type'],
            'generated_events_count': len(generated_events),
            'generated_event_types': list(set(e['event_type'] for e in generated_events)),
            'processed_at': datetime.utcnow()
        }

        self.notification_service.send(notification)

    def _update_metrics(
        self,
        workforce_event: Dict[str, Any],
        generated_events: List[Dict[str, Any]]
    ):
        """Update processing metrics"""
        # Implementation would update monitoring metrics
        pass

    def _handle_processing_error(
        self,
        workforce_event: Dict[str, Any],
        error: Exception
    ):
        """Handle event processing errors"""
        error_record = {
            'workforce_event_id': workforce_event['event_id'],
            'employee_id': workforce_event['employee_id'],
            'event_type': workforce_event['event_type'],
            'error_message': str(error),
            'error_timestamp': datetime.utcnow(),
            'retry_count': 0
        }

        # Log error and potentially queue for retry
        print(f"Error processing workforce event: {error_record}")
```

### dbt Models for Event Correlation
```sql
-- int_workforce_dc_correlation.sql
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['intermediate', 'workforce_integration', 'correlation']
) }}

WITH workforce_events AS (
    SELECT
        event_id as workforce_event_id,
        employee_id,
        event_type as workforce_event_type,
        effective_date,
        created_at as workforce_created_at
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('hire', 'termination', 'promotion', 'merit')
),
dc_plan_events AS (
    SELECT
        event_id as dc_event_id,
        employee_id,
        event_type as dc_event_type,
        effective_date,
        correlation_id,
        created_at as dc_created_at
    FROM {{ ref('fct_retirement_events') }}
    WHERE correlation_id IS NOT NULL
),
correlated_events AS (
    SELECT
        we.workforce_event_id,
        we.employee_id,
        we.workforce_event_type,
        we.effective_date,
        we.workforce_created_at,
        de.dc_event_id,
        de.dc_event_type,
        de.dc_created_at,
        DATEDIFF('second', we.workforce_created_at, de.dc_created_at) as processing_delay_seconds
    FROM workforce_events we
    JOIN dc_plan_events de ON we.event_id = de.correlation_id
)
SELECT
    *,
    CASE
        WHEN processing_delay_seconds <= 60 THEN 'real_time'
        WHEN processing_delay_seconds <= 300 THEN 'near_real_time'
        WHEN processing_delay_seconds <= 3600 THEN 'delayed'
        ELSE 'severely_delayed'
    END as processing_speed_category
FROM correlated_events
```

## Implementation Tasks

### Phase 1: Event Handlers
- [ ] **Implement workforce event handlers** for hire, termination, compensation
- [ ] **Create event routing infrastructure** with handler registration
- [ ] **Build event correlation tracking** for audit trail
- [ ] **Add comprehensive unit tests** for all handlers

### Phase 2: Integration Pipeline
- [ ] **Create workforce event monitor** for real-time processing
- [ ] **Implement error handling** and retry logic
- [ ] **Build notification system** for event processing status
- [ ] **Add performance monitoring** and metrics collection

### Phase 3: Advanced Features
- [ ] **Create dbt models** for event correlation analysis
- [ ] **Implement leave of absence handling** for service computation
- [ ] **Build rehire processing** with vesting restoration
- [ ] **Add integration testing** with workforce simulation

## Dependencies

- **Existing workforce events**: `fct_yearly_events` table
- **S072**: Event Schema (defines DC plan events)
- **S076**: Vesting Management (for termination processing)
- **S079**: HCE Determination (for compensation events)
- **Event processing pipeline**: Real-time event handling

## Success Metrics

### Integration Requirements
- [ ] **Event processing latency**: <60 seconds from workforce to DC plan event
- [ ] **Processing accuracy**: 100% of eligible workforce events trigger appropriate DC plan actions
- [ ] **Error rate**: <0.1% event processing failures
- [ ] **Correlation tracking**: Complete audit trail for all integrated events

### Business Logic Requirements
- [ ] **Eligibility triggers**: 100% accuracy on hire events
- [ ] **Forfeiture processing**: Zero missed forfeitures on termination
- [ ] **HCE recalculation**: Real-time updates on compensation changes
- [ ] **Service computation**: Correct handling of leave events

## Definition of Done

- [ ] **Complete event handler framework** for all workforce event types
- [ ] **Real-time integration** with workforce simulation events
- [ ] **Event correlation tracking** with complete audit trail
- [ ] **Error handling and retry logic** for resilient processing
- [ ] **Performance monitoring** meeting enterprise requirements
- [ ] **Comprehensive testing** including integration scenarios
- [ ] **Documentation** with event flow diagrams
- [ ] **Operational monitoring** for production deployments
