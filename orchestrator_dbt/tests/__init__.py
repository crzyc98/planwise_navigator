"""
Comprehensive test suite for orchestrator_dbt event generation components.

This package provides complete test coverage for the migrated event generation
system from Story S031-03, ensuring all components maintain functionality
and precision while achieving performance improvements.

Test Modules:
- test_event_generation_components: Core component tests for all migrated modules
- Additional test modules can be added here as the system evolves

Usage:
    # Run all tests
    python -m orchestrator_dbt.tests.test_event_generation_components

    # Run specific test class
    python -m unittest orchestrator_dbt.tests.test_event_generation_components.TestBatchEventGenerator

    # Run with coverage
    python -m coverage run orchestrator_dbt/tests/test_event_generation_components.py
    python -m coverage report

Test Coverage Includes:
- BatchEventGenerator: Event generation with batch SQL optimizations
- WorkforceCalculator: Workforce requirement calculations
- CompensationProcessor: Financial precision and proration logic
- EligibilityProcessor: DC plan eligibility determination
- UnifiedIDGenerator: Employee ID generation and validation
- Integration tests: End-to-end workflow validation
- Performance regression tests: Validate improvement targets
"""

from .test_event_generation_components import (
    TestBatchEventGenerator,
    TestWorkforceCalculator,
    TestCompensationProcessor,
    TestEligibilityProcessor,
    TestUnifiedIDGenerator,
    TestEventGenerationIntegration,
    run_comprehensive_test_suite
)

__all__ = [
    'TestBatchEventGenerator',
    'TestWorkforceCalculator',
    'TestCompensationProcessor',
    'TestEligibilityProcessor',
    'TestUnifiedIDGenerator',
    'TestEventGenerationIntegration',
    'run_comprehensive_test_suite'
]
