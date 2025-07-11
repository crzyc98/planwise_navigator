# filename: tests/unit/test_simulation_event.py
"""Unit tests for the unified SimulationEvent model with Pydantic v2."""

import pytest
from datetime import date, datetime
from uuid import UUID, uuid4
from decimal import Decimal
from typing import Any, Dict
from pydantic import ValidationError

from config.events import SimulationEvent, EventFactory, WorkforceEventFactory, HirePayload


class TestSimulationEvent:
    """Test cases for the core SimulationEvent model"""

    def test_event_creation_with_required_fields(self):
        """Test creating event with all required fields"""
        # Use WorkforceEventFactory to create a valid event with payload
        event = WorkforceEventFactory.create_hire_event(
            employee_id='EMP001',
            scenario_id='SCENARIO_001',
            plan_design_id='PLAN_001',
            hire_date=date(2025, 1, 15),
            department='Test Dept',
            job_level=3,
            annual_compensation=Decimal('100000')
        )

        assert event.employee_id == 'EMP001'
        assert event.effective_date == date(2025, 1, 15)
        assert event.scenario_id == 'SCENARIO_001'
        assert event.plan_design_id == 'PLAN_001'
        assert event.source_system == 'workforce_simulation'
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.created_at, datetime)
        assert isinstance(event.payload, HirePayload)
        assert event.correlation_id is None

    def test_event_creation_with_optional_fields(self):
        """Test creating event with optional fields"""
        # Create event with payload and correlation ID
        event_data = {
            'employee_id': 'EMP002',
            'effective_date': date(2025, 1, 15),
            'scenario_id': 'SCENARIO_002',
            'plan_design_id': 'PLAN_002',
            'source_system': 'test_system',
            'correlation_id': 'CORR_001',
            'payload': {
                'event_type': 'hire',
                'hire_date': date(2025, 1, 15),
                'department': 'Test Dept',
                'job_level': 2,
                'annual_compensation': Decimal('80000')
            }
        }

        event = SimulationEvent(**event_data)

        assert event.correlation_id == 'CORR_001'

    def test_uuid_generation(self):
        """Test that unique UUIDs are generated for each event"""
        event1 = WorkforceEventFactory.create_hire_event(
            employee_id='EMP001',
            scenario_id='SCENARIO_001',
            plan_design_id='PLAN_001',
            hire_date=date(2025, 1, 15),
            department='Test Dept',
            job_level=3,
            annual_compensation=Decimal('100000')
        )

        event2 = WorkforceEventFactory.create_hire_event(
            employee_id='EMP002',
            scenario_id='SCENARIO_001',
            plan_design_id='PLAN_001',
            hire_date=date(2025, 1, 15),
            department='Test Dept',
            job_level=3,
            annual_compensation=Decimal('100000')
        )

        assert event1.event_id != event2.event_id
        assert isinstance(event1.event_id, UUID)
        assert isinstance(event2.event_id, UUID)

    def test_timestamp_generation(self):
        """Test that timestamps are automatically generated"""
        event = WorkforceEventFactory.create_hire_event(
            employee_id='EMP001',
            scenario_id='SCENARIO_001',
            plan_design_id='PLAN_001',
            hire_date=date(2025, 1, 15),
            department='Test Dept',
            job_level=3,
            annual_compensation=Decimal('100000')
        )

        assert isinstance(event.created_at, datetime)
        assert event.created_at <= datetime.utcnow()

    def test_missing_required_fields(self):
        """Test validation of required fields"""
        with pytest.raises(ValidationError):
            SimulationEvent()

    def test_empty_employee_id_validation(self):
        """Test validation of empty employee_id"""
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            SimulationEvent(
                employee_id='',
                effective_date=date(2025, 1, 15),
                scenario_id='SCENARIO_001',
                plan_design_id='PLAN_001',
                source_system='test_system',
                payload={
                    'event_type': 'hire',
                    'hire_date': date(2025, 1, 15),
                    'department': 'Test',
                    'job_level': 1,
                    'annual_compensation': Decimal('50000')
                }
            )

    def test_whitespace_employee_id_validation(self):
        """Test validation of whitespace-only employee_id"""
        with pytest.raises(ValueError, match="employee_id cannot be empty"):
            SimulationEvent(
                employee_id='   ',
                effective_date=date(2025, 1, 15),
                scenario_id='SCENARIO_001',
                plan_design_id='PLAN_001',
                source_system='test_system',
                payload={
                    'event_type': 'hire',
                    'hire_date': date(2025, 1, 15),
                    'department': 'Test',
                    'job_level': 1,
                    'annual_compensation': Decimal('50000')
                }
            )

    def test_empty_scenario_id_validation(self):
        """Test validation of empty scenario_id"""
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            SimulationEvent(
                employee_id='EMP001',
                effective_date=date(2025, 1, 15),
                scenario_id='',
                plan_design_id='PLAN_001',
                source_system='test_system',
                payload={
                    'event_type': 'hire',
                    'hire_date': date(2025, 1, 15),
                    'department': 'Test',
                    'job_level': 1,
                    'annual_compensation': Decimal('50000')
                }
            )

    def test_empty_plan_design_id_validation(self):
        """Test validation of empty plan_design_id"""
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            SimulationEvent(
                employee_id='EMP001',
                effective_date=date(2025, 1, 15),
                scenario_id='SCENARIO_001',
                plan_design_id='',
                source_system='test_system',
                payload={
                    'event_type': 'hire',
                    'hire_date': date(2025, 1, 15),
                    'department': 'Test',
                    'job_level': 1,
                    'annual_compensation': Decimal('50000')
                }
            )

    def test_string_trimming(self):
        """Test that string fields are properly trimmed"""
        event = SimulationEvent(
            employee_id='  EMP001  ',
            effective_date=date(2025, 1, 15),
            scenario_id='  SCENARIO_001  ',
            plan_design_id='  PLAN_001  ',
            source_system='test_system',
            payload={
                'event_type': 'hire',
                'hire_date': date(2025, 1, 15),
                'department': 'Test',
                'job_level': 1,
                'annual_compensation': Decimal('50000')
            }
        )

        assert event.employee_id == 'EMP001'
        assert event.scenario_id == 'SCENARIO_001'
        assert event.plan_design_id == 'PLAN_001'

    def test_model_config_extra_forbid(self):
        """Test that extra fields are forbidden"""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            SimulationEvent(
                employee_id='EMP001',
                effective_date=date(2025, 1, 15),
                scenario_id='SCENARIO_001',
                plan_design_id='PLAN_001',
                source_system='test_system',
                payload={
                    'event_type': 'hire',
                    'hire_date': date(2025, 1, 15),
                    'department': 'Test',
                    'job_level': 1,
                    'annual_compensation': Decimal('50000')
                },
                unexpected_field='should_fail'
            )

    def test_serialization_to_dict(self):
        """Test serialization to dictionary"""
        event = WorkforceEventFactory.create_hire_event(
            employee_id='EMP001',
            scenario_id='SCENARIO_001',
            plan_design_id='PLAN_001',
            hire_date=date(2025, 1, 15),
            department='Test Dept',
            job_level=3,
            annual_compensation=Decimal('100000')
        )

        event_dict = event.model_dump()

        assert event_dict['employee_id'] == 'EMP001'
        assert event_dict['effective_date'] == date(2025, 1, 15)
        assert event_dict['scenario_id'] == 'SCENARIO_001'
        assert event_dict['plan_design_id'] == 'PLAN_001'
        assert event_dict['source_system'] == 'workforce_simulation'
        assert 'event_id' in event_dict
        assert 'created_at' in event_dict
        assert 'payload' in event_dict

    def test_deserialization_from_dict(self):
        """Test deserialization from dictionary"""
        event_data = {
            'event_id': str(uuid4()),
            'employee_id': 'EMP001',
            'effective_date': '2025-01-15',
            'created_at': '2025-01-15T10:30:00',
            'scenario_id': 'SCENARIO_001',
            'plan_design_id': 'PLAN_001',
            'source_system': 'test_system',
            'correlation_id': 'CORR_001',
            'payload': {
                'event_type': 'hire',
                'hire_date': '2025-01-15',
                'department': 'Test',
                'job_level': 3,
                'annual_compensation': '100000'
            }
        }

        event = SimulationEvent.model_validate(event_data)

        assert event.employee_id == 'EMP001'
        assert event.effective_date == date(2025, 1, 15)
        assert event.scenario_id == 'SCENARIO_001'
        assert event.correlation_id == 'CORR_001'



class TestEventFactory:
    """Test cases for EventFactory"""

    def test_create_event_from_dict(self):
        """Test creating event from dictionary"""
        event_data = {
            'employee_id': 'EMP001',
            'effective_date': '2025-01-15',
            'scenario_id': 'SCENARIO_001',
            'plan_design_id': 'PLAN_001',
            'source_system': 'test_system',
            'payload': {
                'event_type': 'hire',
                'hire_date': '2025-01-15',
                'department': 'Test',
                'job_level': 3,
                'annual_compensation': '100000'
            }
        }

        event = EventFactory.create_event(event_data)

        assert isinstance(event, SimulationEvent)
        assert event.employee_id == 'EMP001'
        assert event.effective_date == date(2025, 1, 15)

    def test_validate_schema(self):
        """Test schema validation without creating instance"""
        event_data = {
            'employee_id': 'EMP001',
            'effective_date': '2025-01-15',
            'scenario_id': 'SCENARIO_001',
            'plan_design_id': 'PLAN_001',
            'source_system': 'test_system',
            'payload': {
                'event_type': 'hire',
                'hire_date': '2025-01-15',
                'department': 'Test',
                'job_level': 3,
                'annual_compensation': '100000'
            }
        }

        validated_data = EventFactory.validate_schema(event_data)

        assert validated_data['employee_id'] == 'EMP001'
        assert validated_data['effective_date'] == date(2025, 1, 15)
        assert 'event_id' in validated_data
        assert 'created_at' in validated_data

    def test_create_basic_event_deprecated(self):
        """Test that create_basic_event is deprecated"""
        with pytest.raises(NotImplementedError, match="create_basic_event is deprecated"):
            EventFactory.create_basic_event(
                employee_id='EMP001',
                effective_date=date(2025, 1, 15),
                scenario_id='SCENARIO_001',
                plan_design_id='PLAN_001'
            )

    def test_invalid_data_handling(self):
        """Test handling of invalid data"""
        invalid_data = {
            'employee_id': '',  # Empty employee_id should fail
            'effective_date': '2025-01-15',
            'scenario_id': 'SCENARIO_001',
            'plan_design_id': 'PLAN_001',
            'source_system': 'test_system',
            'payload': {
                'event_type': 'hire',
                'hire_date': '2025-01-15',
                'department': 'Test',
                'job_level': 3,
                'annual_compensation': '100000'
            }
        }

        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            EventFactory.create_event(invalid_data)


class TestPerformance:
    """Performance tests for event model"""

    def test_event_creation_performance(self):
        """Test performance of creating multiple events"""
        import time

        start_time = time.time()

        events = []
        for i in range(1000):
            event = WorkforceEventFactory.create_hire_event(
                employee_id=f'EMP{i:06d}',
                scenario_id='SCENARIO_001',
                plan_design_id='PLAN_001',
                hire_date=date(2025, 1, 15),
                department='Test',
                job_level=3,
                annual_compensation=Decimal('100000')
            )
            events.append(event)

        end_time = time.time()
        creation_time = end_time - start_time

        # Should create 1000 events in less than 1 second
        assert creation_time < 1.0
        assert len(events) == 1000

    def test_serialization_performance(self):
        """Test performance of serializing events"""
        import time

        events = []
        for i in range(100):
            event = WorkforceEventFactory.create_hire_event(
                employee_id=f'EMP{i:06d}',
                scenario_id='SCENARIO_001',
                plan_design_id='PLAN_001',
                hire_date=date(2025, 1, 15),
                department='Test',
                job_level=3,
                annual_compensation=Decimal('100000')
            )
            events.append(event)

        start_time = time.time()

        serialized_events = [event.model_dump() for event in events]

        end_time = time.time()
        serialization_time = end_time - start_time

        # Should serialize 100 events in less than 0.1 seconds
        assert serialization_time < 0.1
        assert len(serialized_events) == 100
