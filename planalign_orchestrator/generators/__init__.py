"""
Event Generator Abstraction Layer

This package provides the event type abstraction layer for PlanAlign Engine.
It enables adding new workforce event types by implementing a single interface
and registering in one location.

Key Components:
- EventGenerator: Abstract base class for all event generators
- EventRegistry: Centralized registration and lookup
- EventContext: Runtime context passed to generators
- ValidationResult: Result of event validation
- GeneratorMetrics: Structured logging output
- HazardBasedEventGeneratorMixin: Mixin for hazard-based events

Usage:
    from planalign_orchestrator.generators import (
        EventGenerator,
        EventRegistry,
        EventContext,
        ValidationResult,
    )

    @EventRegistry.register("my_event")
    class MyEventGenerator(EventGenerator):
        event_type = "my_event"
        execution_order = 50
        ...
"""

from planalign_orchestrator.generators.base import (
    EventGenerator,
    EventContext,
    ValidationResult,
    GeneratorMetrics,
    HazardBasedEventGeneratorMixin,
)
from planalign_orchestrator.generators.registry import EventRegistry

# Import generators to trigger registration via @EventRegistry.register decorator
# Core workforce events (T022-T026)
from planalign_orchestrator.generators.termination import TerminationEventGenerator
from planalign_orchestrator.generators.hire import HireEventGenerator
from planalign_orchestrator.generators.promotion import PromotionEventGenerator
from planalign_orchestrator.generators.merit import MeritEventGenerator
from planalign_orchestrator.generators.enrollment import EnrollmentEventGenerator
# Example new event type (US1 - E004)
from planalign_orchestrator.generators.sabbatical import SabbaticalEventGenerator

__all__ = [
    # Base classes
    "EventGenerator",
    "EventRegistry",
    "EventContext",
    "ValidationResult",
    "GeneratorMetrics",
    "HazardBasedEventGeneratorMixin",
    # Core workforce generators
    "TerminationEventGenerator",
    "HireEventGenerator",
    "PromotionEventGenerator",
    "MeritEventGenerator",
    "EnrollmentEventGenerator",
    # Extended event types
    "SabbaticalEventGenerator",
]
