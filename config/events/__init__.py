# filename: config/events/__init__.py
"""
Events package for Fidelity PlanAlign Engine.

This package contains modularized event payloads, validators, and factories
organized by domain (workforce, dc_plan, admin).

Submodules:
- validators: Shared Decimal quantization helpers
- workforce: HirePayload, PromotionPayload, TerminationPayload, MeritPayload, SabbaticalPayload
- dc_plan: EligibilityPayload, EnrollmentPayload, ContributionPayload, VestingPayload, etc.
- admin: ForfeiturePayload, HCEStatusPayload, ComplianceEventPayload
- core: SimulationEvent and factory classes
"""

# Validators
from .validators import (
    quantize_amount,
    quantize_rate,
    quantize_amount_dict,
    quantize_rate_optional,
)

# Workforce payloads
from .workforce import (
    HirePayload,
    PromotionPayload,
    TerminationPayload,
    MeritPayload,
    SabbaticalPayload,
)

# DC Plan payloads
from .dc_plan import (
    EligibilityPayload,
    EnrollmentPayload,
    ContributionPayload,
    VestingPayload,
    AutoEnrollmentWindowPayload,
    EnrollmentChangePayload,
)

# Admin payloads
from .admin import (
    ForfeiturePayload,
    HCEStatusPayload,
    ComplianceEventPayload,
)

# Core event model and factories
from .core import (
    SimulationEvent,
    LegacySimulationEvent,
    EventFactory,
    WorkforceEventFactory,
    DCPlanEventFactory,
    PlanAdministrationEventFactory,
)

# Re-export from orchestrator for backward compatibility
from planalign_orchestrator.generators import (
    EventRegistry,
    EventGenerator,
    EventContext,
    ValidationResult,
    GeneratorMetrics,
)

__all__ = [
    # Validators
    "quantize_amount",
    "quantize_rate",
    "quantize_amount_dict",
    "quantize_rate_optional",
    # Workforce payloads
    "HirePayload",
    "PromotionPayload",
    "TerminationPayload",
    "MeritPayload",
    "SabbaticalPayload",
    # DC Plan payloads
    "EligibilityPayload",
    "EnrollmentPayload",
    "ContributionPayload",
    "VestingPayload",
    "AutoEnrollmentWindowPayload",
    "EnrollmentChangePayload",
    # Admin payloads
    "ForfeiturePayload",
    "HCEStatusPayload",
    "ComplianceEventPayload",
    # Core event model
    "SimulationEvent",
    "LegacySimulationEvent",
    # Factories
    "EventFactory",
    "WorkforceEventFactory",
    "DCPlanEventFactory",
    "PlanAdministrationEventFactory",
    # Event Generator Abstraction Layer (E004)
    "EventRegistry",
    "EventGenerator",
    "EventContext",
    "ValidationResult",
    "GeneratorMetrics",
]
