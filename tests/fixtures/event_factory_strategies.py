"""Hypothesis strategies and contracts for simulation event factories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from calendar import isleap
from typing import Any, Callable, Mapping

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy
from pydantic import BaseModel

from planalign_core.events import (
    AutoEnrollmentOptions,
    ContributionPayload,
    DCPlanEventFactory,
    EnrollmentPayload,
    ForfeiturePayload,
    HCEStatusPayload,
    HirePayload,
    MeritPayload,
    PlanAdministrationEventFactory,
    PromotionPayload,
    SimulationEvent,
    TerminationPayload,
    VestingPayload,
    WorkforceEventFactory,
)

FactoryArguments = dict[str, Any]
EventFactory = Callable[..., SimulationEvent]
JsonTypes = tuple[type[object], ...]

MIN_TEST_YEAR = 2000
MAX_TEST_YEAR = 2099
MAX_TEST_AMOUNT = Decimal("1000000000.000000")

SIMULATION_YEARS = st.integers(min_value=MIN_TEST_YEAR, max_value=MAX_TEST_YEAR)
POSITIVE_AMOUNTS = st.decimals(
    min_value=Decimal("0.000001"),
    max_value=MAX_TEST_AMOUNT,
    places=6,
    allow_nan=False,
    allow_infinity=False,
)
NONNEGATIVE_AMOUNTS = st.decimals(
    min_value=Decimal("0"),
    max_value=MAX_TEST_AMOUNT,
    places=6,
    allow_nan=False,
    allow_infinity=False,
)
RATES = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1"),
    places=4,
    allow_nan=False,
    allow_infinity=False,
)
SIGNED_AMOUNTS = st.decimals(
    min_value=-MAX_TEST_AMOUNT,
    max_value=MAX_TEST_AMOUNT,
    places=6,
    allow_nan=False,
    allow_infinity=False,
)
WORKFORCE_OVERPRECISION_AMOUNTS = st.decimals(
    min_value=Decimal("0.0000006"),
    max_value=Decimal("1000000"),
    places=9,
    allow_nan=False,
    allow_infinity=False,
)
OVERPRECISION_RATES = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1"),
    places=7,
    allow_nan=False,
    allow_infinity=False,
)
CONSTRAINED_OVERSCALE_AMOUNTS = st.tuples(
    st.integers(min_value=0, max_value=10**13),
    st.integers(min_value=1, max_value=9),
).map(lambda parts: Decimal(parts[0] * 10 + parts[1]).scaleb(-7))
CONSTRAINED_OVERSCALE_RATES = st.tuples(
    st.integers(min_value=0, max_value=9999),
    st.integers(min_value=1, max_value=9),
).map(lambda parts: Decimal(parts[0] * 10 + parts[1]).scaleb(-5))
RATE_BOUNDARIES = st.sampled_from((Decimal("0"), Decimal("1")))
WHITESPACE_ONLY_IDS = st.sampled_from(("", " ", "\t", "\n", "\u00a0"))
NEGATIVE_AMOUNTS = st.decimals(
    min_value=Decimal("-1000000"),
    max_value=Decimal("-0.000001"),
    places=6,
    allow_nan=False,
    allow_infinity=False,
)
NONPOSITIVE_AMOUNTS = st.one_of(st.just(Decimal("0")), NEGATIVE_AMOUNTS)
SUBQUANTUM_POSITIVE_AMOUNTS = st.sampled_from(
    (Decimal("0.0000001"), Decimal("0.0000004"), Decimal("0.0000005"))
)
INVALID_RATES = st.one_of(
    st.decimals(
        min_value=Decimal("-10"),
        max_value=Decimal("-0.0001"),
        places=4,
        allow_nan=False,
        allow_infinity=False,
    ),
    st.decimals(
        min_value=Decimal("1.0001"),
        max_value=Decimal("10"),
        places=4,
        allow_nan=False,
        allow_infinity=False,
    ),
)

_READABLE_CHARACTERS = st.characters(
    blacklist_categories=("Cc", "Cf", "Cs", "Zl", "Zp", "Zs")
)
IDENTIFIER_CORES = st.text(
    alphabet=_READABLE_CHARACTERS,
    min_size=1,
    max_size=24,
)
VALID_IDENTIFIERS = st.builds(
    lambda prefix, core, suffix: f"{prefix}{core}{suffix}",
    st.sampled_from(("", " ", "\t")),
    IDENTIFIER_CORES,
    st.sampled_from(("", " ", "\n")),
)
VALID_PAYLOAD_IDS = IDENTIFIER_CORES
OPTIONAL_PLAN_IDS = st.one_of(st.none(), VALID_PAYLOAD_IDS)
COMMON_CONTEXTS: SearchStrategy[FactoryArguments] = st.fixed_dictionaries(
    {
        "employee_id": VALID_IDENTIFIERS,
        "scenario_id": VALID_IDENTIFIERS,
        "plan_design_id": VALID_IDENTIFIERS,
    }
)


def dates_for_year(year: int) -> SearchStrategy[date]:
    """Return dates bounded to one simulation year."""
    return st.dates(
        min_value=date(year, 1, 1),
        max_value=date(year, 12, 31),
    )


@dataclass(frozen=True)
class GeneratedEventInput:
    """Generated valid factory arguments with their simulation-year context."""

    simulation_year: int
    arguments: FactoryArguments
    expected_effective_date: date


@dataclass(frozen=True)
class EventFactorySpec:
    """Static contract for one public event factory."""

    name: str
    factory: EventFactory
    payload_type: type[BaseModel]
    event_type: str
    source_system: str
    effective_date_argument: str
    payload_json_types: Mapping[str, JsonTypes]
    amount_fields: tuple[str, ...] = ()
    rate_fields: tuple[str, ...] = ()
    nested_amount_fields: tuple[str, ...] = ()

    @property
    def payload_keys(self) -> frozenset[str]:
        """Return the exact payload key contract."""
        return frozenset(self.payload_json_types)


@dataclass(frozen=True)
class EventFactoryCase:
    """Factory contract bound to its valid generated-input strategy."""

    spec: EventFactorySpec
    arguments: SearchStrategy[GeneratedEventInput]


@dataclass(frozen=True)
class EmployeeLifecyclePair:
    """Generated same-year hire and termination inputs for one employee."""

    employee_id: str
    simulation_year: int
    hire_arguments: FactoryArguments
    termination_arguments: FactoryArguments
    hire_date: date
    termination_date: date


@dataclass(frozen=True)
class InvalidEventInput:
    """Otherwise-valid factory arguments with one deliberate invalid value."""

    case: EventFactoryCase
    arguments: FactoryArguments
    invalid_field: str
    invalid_category: str


ENVELOPE_JSON_TYPES: Mapping[str, JsonTypes] = {
    "event_id": (str,),
    "employee_id": (str,),
    "effective_date": (str,),
    "created_at": (str,),
    "scenario_id": (str,),
    "plan_design_id": (str,),
    "source_system": (str,),
    "payload": (dict,),
    "correlation_id": (str, type(None)),
}

EVENT_FACTORY_SPECS = (
    EventFactorySpec(
        name="hire",
        factory=WorkforceEventFactory.create_hire_event,
        payload_type=HirePayload,
        event_type="hire",
        source_system="workforce_simulation",
        effective_date_argument="hire_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str, type(None)),
            "hire_date": (str,),
            "department": (str,),
            "job_level": (int,),
            "annual_compensation": (str,),
        },
        amount_fields=("annual_compensation",),
    ),
    EventFactorySpec(
        name="termination",
        factory=WorkforceEventFactory.create_termination_event,
        payload_type=TerminationPayload,
        event_type="termination",
        source_system="workforce_simulation",
        effective_date_argument="effective_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str, type(None)),
            "termination_reason": (str,),
            "final_pay_date": (str,),
        },
    ),
    EventFactorySpec(
        name="promotion",
        factory=WorkforceEventFactory.create_promotion_event,
        payload_type=PromotionPayload,
        event_type="promotion",
        source_system="workforce_simulation",
        effective_date_argument="effective_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str, type(None)),
            "new_job_level": (int,),
            "new_annual_compensation": (str,),
            "effective_date": (str,),
        },
        amount_fields=("new_annual_compensation",),
    ),
    EventFactorySpec(
        name="merit",
        factory=WorkforceEventFactory.create_merit_event,
        payload_type=MeritPayload,
        event_type="merit",
        source_system="workforce_simulation",
        effective_date_argument="effective_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str, type(None)),
            "new_compensation": (str,),
            "merit_percentage": (str,),
        },
        amount_fields=("new_compensation",),
        rate_fields=("merit_percentage",),
    ),
    EventFactorySpec(
        name="enrollment",
        factory=DCPlanEventFactory.create_enrollment_event,
        payload_type=EnrollmentPayload,
        event_type="enrollment",
        source_system="dc_plan_administration",
        effective_date_argument="enrollment_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str,),
            "enrollment_date": (str,),
            "pre_tax_contribution_rate": (str,),
            "roth_contribution_rate": (str,),
            "after_tax_contribution_rate": (str,),
            "auto_enrollment": (bool,),
            "opt_out_window_expires": (str, type(None)),
            "enrollment_source": (str,),
            "auto_enrollment_window_start": (str, type(None)),
            "auto_enrollment_window_end": (str, type(None)),
            "proactive_enrollment_eligible": (bool,),
            "window_timing_compliant": (bool,),
        },
        rate_fields=(
            "pre_tax_contribution_rate",
            "roth_contribution_rate",
            "after_tax_contribution_rate",
        ),
    ),
    EventFactorySpec(
        name="contribution",
        factory=DCPlanEventFactory.create_contribution_event,
        payload_type=ContributionPayload,
        event_type="contribution",
        source_system="dc_plan_administration",
        effective_date_argument="contribution_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str,),
            "source": (str,),
            "amount": (str,),
            "pay_period_end": (str,),
            "contribution_date": (str,),
            "ytd_amount": (str,),
            "payroll_id": (str,),
            "irs_limit_applied": (bool,),
            "inferred_value": (bool,),
        },
        amount_fields=("amount", "ytd_amount"),
    ),
    EventFactorySpec(
        name="vesting",
        factory=DCPlanEventFactory.create_vesting_event,
        payload_type=VestingPayload,
        event_type="vesting",
        source_system="dc_plan_administration",
        effective_date_argument="service_computation_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str,),
            "vested_percentage": (str,),
            "source_balances_vested": (dict,),
            "vesting_schedule_type": (str,),
            "service_computation_date": (str,),
            "service_credited_hours": (int,),
            "service_period_end_date": (str,),
        },
        rate_fields=("vested_percentage",),
        nested_amount_fields=("source_balances_vested",),
    ),
    EventFactorySpec(
        name="forfeiture",
        factory=PlanAdministrationEventFactory.create_forfeiture_event,
        payload_type=ForfeiturePayload,
        event_type="forfeiture",
        source_system="plan_administration",
        effective_date_argument="effective_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str,),
            "forfeited_from_source": (str,),
            "amount": (str,),
            "reason": (str,),
            "vested_percentage": (str,),
        },
        amount_fields=("amount",),
        rate_fields=("vested_percentage",),
    ),
    EventFactorySpec(
        name="hce_status",
        factory=PlanAdministrationEventFactory.create_hce_status_event,
        payload_type=HCEStatusPayload,
        event_type="hce_status",
        source_system="hce_determination",
        effective_date_argument="determination_date",
        payload_json_types={
            "event_type": (str,),
            "plan_id": (str,),
            "determination_method": (str,),
            "ytd_compensation": (str,),
            "annualized_compensation": (str,),
            "hce_threshold": (str,),
            "is_hce": (bool,),
            "determination_date": (str,),
            "prior_year_hce": (bool, type(None)),
        },
        amount_fields=(
            "ytd_compensation",
            "annualized_compensation",
            "hce_threshold",
        ),
    ),
)

EVENT_FACTORY_SPEC_BY_NAME = {spec.name: spec for spec in EVENT_FACTORY_SPECS}

UNICODE_IDENTIFIER_EXAMPLES = (
    "EMP_é",
    "EMP_e\u0301",
    "员工_退休",
    "EMP_🧮",
    "  EMP_é  ",
)

_TERMINATION_REASONS = st.sampled_from(
    ("voluntary", "involuntary", "retirement", "death", "disability")
)
_CONTRIBUTION_SOURCES = st.sampled_from(
    (
        "employee_pre_tax",
        "employee_roth",
        "employee_after_tax",
        "employee_catch_up",
        "employer_match",
        "employer_match_true_up",
        "employer_nonelective",
        "employer_profit_sharing",
        "forfeiture_allocation",
    )
)
_VESTING_SOURCES = st.sampled_from(
    ("employer_match", "employer_nonelective", "employer_profit_sharing")
)


def _hire_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    return {
        "hire_date": event_date,
        "department": draw(IDENTIFIER_CORES),
        "job_level": draw(st.integers(min_value=1, max_value=10)),
        "annual_compensation": draw(POSITIVE_AMOUNTS),
        "plan_id": draw(OPTIONAL_PLAN_IDS),
    }


def _termination_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    return {
        "effective_date": event_date,
        "termination_reason": draw(_TERMINATION_REASONS),
        "final_pay_date": draw(dates_for_year(year)),
        "plan_id": draw(OPTIONAL_PLAN_IDS),
    }


def _promotion_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    return {
        "effective_date": event_date,
        "new_job_level": draw(st.integers(min_value=1, max_value=10)),
        "new_annual_compensation": draw(POSITIVE_AMOUNTS),
        "plan_id": draw(OPTIONAL_PLAN_IDS),
    }


def _merit_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    return {
        "effective_date": event_date,
        "new_compensation": draw(POSITIVE_AMOUNTS),
        "merit_percentage": draw(RATES),
        "plan_id": draw(OPTIONAL_PLAN_IDS),
    }


def _optional_date(draw: Any, year: int) -> date | None:
    return draw(st.one_of(st.none(), dates_for_year(year)))


def _enrollment_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    options = AutoEnrollmentOptions(
        auto_enrollment=draw(st.booleans()),
        opt_out_window_expires=_optional_date(draw, year),
        enrollment_source=draw(st.sampled_from(("proactive", "auto", "voluntary"))),
        auto_enrollment_window_start=_optional_date(draw, year),
        auto_enrollment_window_end=_optional_date(draw, year),
        proactive_enrollment_eligible=draw(st.booleans()),
        window_timing_compliant=draw(st.booleans()),
    )
    return {
        "plan_id": draw(VALID_PAYLOAD_IDS),
        "enrollment_date": event_date,
        "pre_tax_contribution_rate": draw(RATES),
        "roth_contribution_rate": draw(RATES),
        "after_tax_contribution_rate": draw(RATES),
        "auto_enrollment_options": options,
    }


def _contribution_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    return {
        "plan_id": draw(VALID_PAYLOAD_IDS),
        "source": draw(_CONTRIBUTION_SOURCES),
        "amount": draw(POSITIVE_AMOUNTS),
        "pay_period_end": draw(dates_for_year(year)),
        "contribution_date": event_date,
        "ytd_amount": draw(NONNEGATIVE_AMOUNTS),
        "payroll_id": draw(VALID_PAYLOAD_IDS),
        "irs_limit_applied": draw(st.booleans()),
        "inferred_value": draw(st.booleans()),
    }


def _vesting_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    balances = draw(
        st.dictionaries(
            keys=_VESTING_SOURCES,
            values=NONNEGATIVE_AMOUNTS,
            min_size=0,
            max_size=3,
        )
    )
    return {
        "plan_id": draw(VALID_PAYLOAD_IDS),
        "vested_percentage": draw(RATES),
        "source_balances_vested": balances,
        "vesting_schedule_type": draw(
            st.sampled_from(("graded", "cliff", "immediate"))
        ),
        "service_computation_date": event_date,
        "service_credited_hours": draw(st.integers(min_value=0, max_value=4000)),
        "service_period_end_date": draw(dates_for_year(year)),
    }


def _forfeiture_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    return {
        "plan_id": draw(VALID_PAYLOAD_IDS),
        "forfeited_from_source": draw(_VESTING_SOURCES),
        "amount": draw(POSITIVE_AMOUNTS),
        "reason": draw(st.sampled_from(("unvested_termination", "break_in_service"))),
        "vested_percentage": draw(RATES),
        "effective_date": event_date,
    }


def _hce_arguments(draw: Any, year: int, event_date: date) -> FactoryArguments:
    return {
        "plan_id": draw(VALID_PAYLOAD_IDS),
        "determination_method": draw(st.sampled_from(("prior_year", "current_year"))),
        "ytd_compensation": draw(NONNEGATIVE_AMOUNTS),
        "annualized_compensation": draw(NONNEGATIVE_AMOUNTS),
        "hce_threshold": draw(POSITIVE_AMOUNTS),
        "is_hce": draw(st.booleans()),
        "determination_date": event_date,
        "prior_year_hce": draw(st.one_of(st.none(), st.booleans())),
    }


_ARGUMENT_BUILDERS = {
    "hire": _hire_arguments,
    "termination": _termination_arguments,
    "promotion": _promotion_arguments,
    "merit": _merit_arguments,
    "enrollment": _enrollment_arguments,
    "contribution": _contribution_arguments,
    "vesting": _vesting_arguments,
    "forfeiture": _forfeiture_arguments,
    "hce_status": _hce_arguments,
}


@st.composite
def generated_event_inputs(draw: Any, spec: EventFactorySpec) -> GeneratedEventInput:
    """Generate valid arguments and the expected effective date for a factory."""
    year = draw(SIMULATION_YEARS)
    event_date = draw(dates_for_year(year))
    arguments = dict(draw(COMMON_CONTEXTS))
    arguments.update(_ARGUMENT_BUILDERS[spec.name](draw, year, event_date))
    return GeneratedEventInput(
        simulation_year=year,
        arguments=arguments,
        expected_effective_date=event_date,
    )


EVENT_FACTORY_CASES = tuple(
    EventFactoryCase(spec=spec, arguments=generated_event_inputs(spec))
    for spec in EVENT_FACTORY_SPECS
)

YEAR_BOUNDARY_DATES = SIMULATION_YEARS.flatmap(
    lambda year: st.sampled_from((date(year, 1, 1), date(year, 12, 31)))
)
LEAP_DAYS = st.sampled_from(
    tuple(
        date(year, 2, 29)
        for year in range(MIN_TEST_YEAR, MAX_TEST_YEAR + 1)
        if isleap(year)
    )
)


@st.composite
def employee_lifecycle_pairs(draw: Any) -> EmployeeLifecyclePair:
    """Generate ordered hire/termination events in one simulation year."""
    year = draw(SIMULATION_YEARS)
    hire_date = draw(dates_for_year(year))
    termination_date = draw(st.dates(min_value=hire_date, max_value=date(year, 12, 31)))
    context = dict(draw(COMMON_CONTEXTS))
    hire_arguments = {
        **context,
        "hire_date": hire_date,
        "department": draw(IDENTIFIER_CORES),
        "job_level": draw(st.integers(min_value=1, max_value=10)),
        "annual_compensation": draw(POSITIVE_AMOUNTS),
    }
    termination_arguments = {
        **context,
        "effective_date": termination_date,
        "termination_reason": draw(_TERMINATION_REASONS),
        "final_pay_date": draw(dates_for_year(year)),
    }
    return EmployeeLifecyclePair(
        employee_id=context["employee_id"],
        simulation_year=year,
        hire_arguments=hire_arguments,
        termination_arguments=termination_arguments,
        hire_date=hire_date,
        termination_date=termination_date,
    )


EMPLOYEE_LIFECYCLE_PAIRS = employee_lifecycle_pairs()


@st.composite
def invalid_event_inputs(
    draw: Any,
    case: EventFactoryCase,
    field: str,
    invalid_values: SearchStrategy[Any],
    category: str,
) -> InvalidEventInput:
    """Mutate one field in an otherwise-valid factory argument mapping."""
    generated = draw(case.arguments)
    arguments = dict(generated.arguments)
    arguments[field] = draw(invalid_values)
    return InvalidEventInput(
        case=case,
        arguments=arguments,
        invalid_field=field,
        invalid_category=category,
    )
