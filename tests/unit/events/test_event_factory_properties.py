"""Property-based contracts for the public simulation event factories."""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy
from pydantic import ValidationError

from planalign_core.events import SimulationEvent, WorkforceEventFactory
from tests.fixtures.event_factory_strategies import (
    CONSTRAINED_OVERSCALE_AMOUNTS,
    CONSTRAINED_OVERSCALE_RATES,
    EMPLOYEE_LIFECYCLE_PAIRS,
    ENVELOPE_JSON_TYPES,
    EVENT_FACTORY_CASES,
    INVALID_RATES,
    LEAP_DAYS,
    NEGATIVE_AMOUNTS,
    NONPOSITIVE_AMOUNTS,
    OVERPRECISION_RATES,
    RATE_BOUNDARIES,
    SIGNED_AMOUNTS,
    SUBQUANTUM_POSITIVE_AMOUNTS,
    UNICODE_IDENTIFIER_EXAMPLES,
    WHITESPACE_ONLY_IDS,
    WORKFORCE_OVERPRECISION_AMOUNTS,
    YEAR_BOUNDARY_DATES,
    EmployeeLifecyclePair,
    EventFactoryCase,
    invalid_event_inputs,
)

PROPERTY_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    derandomize=True,
)
CASE_BY_NAME = {case.spec.name: case for case in EVENT_FACTORY_CASES}


def _hire_with_compensation(amount: Decimal) -> SimulationEvent:
    return WorkforceEventFactory.create_hire_event(
        employee_id="EMP001",
        scenario_id="SCENARIO",
        plan_design_id="DESIGN",
        hire_date=date(2025, 1, 1),
        department="Engineering",
        job_level=1,
        annual_compensation=amount,
    )


def _promotion_with_compensation(amount: Decimal) -> SimulationEvent:
    return WorkforceEventFactory.create_promotion_event(
        employee_id="EMP001",
        scenario_id="SCENARIO",
        plan_design_id="DESIGN",
        effective_date=date(2025, 6, 1),
        new_job_level=2,
        new_annual_compensation=amount,
    )


def _merit_with_compensation(amount: Decimal) -> SimulationEvent:
    return WorkforceEventFactory.create_merit_event(
        employee_id="EMP001",
        scenario_id="SCENARIO",
        plan_design_id="DESIGN",
        effective_date=date(2025, 6, 1),
        new_compensation=amount,
        merit_percentage=Decimal("0.0100"),
    )


@pytest.mark.parametrize(
    "factory",
    (_hire_with_compensation, _promotion_with_compensation, _merit_with_compensation),
    ids=("hire", "promotion", "merit"),
)
def test_subquantum_compensation_rejected(
    factory: Callable[[Decimal], SimulationEvent],
) -> None:
    """Positive compensation that normalizes to zero must be rejected."""
    with pytest.raises(ValidationError):
        factory(Decimal("0.0000001"))


@pytest.mark.parametrize(
    "case",
    EVENT_FACTORY_CASES,
    ids=lambda case: case.spec.name,
)
@PROPERTY_SETTINGS
@given(data=st.data())
def test_factory_native_round_trip_and_mapping(
    case: EventFactoryCase,
    data: st.DataObject,
) -> None:
    """Generated-valid factory events retain their complete native contract."""
    generated = data.draw(case.arguments, label=case.spec.name)
    event = case.spec.factory(**generated.arguments)

    assert type(event.payload) is case.spec.payload_type
    assert event.payload.event_type == case.spec.event_type
    assert event.source_system == case.spec.source_system
    assert event.effective_date == generated.expected_effective_date
    assert event.employee_id == generated.arguments["employee_id"].strip()
    assert event.scenario_id == generated.arguments["scenario_id"].strip()
    assert event.plan_design_id == generated.arguments["plan_design_id"].strip()
    assert SimulationEvent.model_validate(event.model_dump()) == event


@pytest.mark.parametrize("employee_id", UNICODE_IDENTIFIER_EXAMPLES)
def test_unicode_identifier_native_round_trip(employee_id: str) -> None:
    """Readable Unicode identifiers retain content after normalization."""
    event = WorkforceEventFactory.create_hire_event(
        employee_id=employee_id,
        scenario_id=" SCENARIO_é ",
        plan_design_id=" DESIGN_退休 ",
        hire_date=date(2025, 1, 1),
        department="Engineering",
        job_level=1,
        annual_compensation=Decimal("50000.000000"),
    )

    assert event.employee_id == employee_id.strip()
    assert event.scenario_id == "SCENARIO_é"
    assert event.plan_design_id == "DESIGN_退休"
    assert SimulationEvent.model_validate(event.model_dump()) == event


@pytest.mark.parametrize(
    "case",
    EVENT_FACTORY_CASES,
    ids=lambda case: case.spec.name,
)
@PROPERTY_SETTINGS
@given(data=st.data())
def test_decimal_discipline(case: EventFactoryCase, data: st.DataObject) -> None:
    """All covered numeric payload values retain exact Decimal scale."""
    generated = data.draw(case.arguments, label=case.spec.name)
    payload = case.spec.factory(**generated.arguments).payload

    for field in case.spec.amount_fields:
        value = getattr(payload, field)
        assert type(value) is Decimal
        assert value.as_tuple().exponent == -6

    for field in case.spec.rate_fields:
        value = getattr(payload, field)
        assert type(value) is Decimal
        assert value.as_tuple().exponent == -4
        assert Decimal("0") <= value <= Decimal("1")

    for field in case.spec.nested_amount_fields:
        for value in getattr(payload, field).values():
            assert type(value) is Decimal
            assert value.as_tuple().exponent == -6


@pytest.mark.parametrize(
    ("factory", "payload_field"),
    (
        (_hire_with_compensation, "annual_compensation"),
        (_promotion_with_compensation, "new_annual_compensation"),
        (_merit_with_compensation, "new_compensation"),
    ),
    ids=("hire", "promotion", "merit"),
)
@PROPERTY_SETTINGS
@given(amount=WORKFORCE_OVERPRECISION_AMOUNTS)
def test_decimal_discipline_workforce_overprecision(
    factory: Callable[[Decimal], SimulationEvent],
    payload_field: str,
    amount: Decimal,
) -> None:
    """Workforce compensation accepts safe overprecision and normalizes it."""
    value = getattr(factory(amount).payload, payload_field)
    assert type(value) is Decimal
    assert value > 0
    assert value.as_tuple().exponent == -6


@PROPERTY_SETTINGS
@given(rate=OVERPRECISION_RATES)
def test_decimal_discipline_merit_rate_overprecision(rate: Decimal) -> None:
    """Merit rates without a decimal_places field normalize to four places."""
    event = WorkforceEventFactory.create_merit_event(
        employee_id="EMP001",
        scenario_id="SCENARIO",
        plan_design_id="DESIGN",
        effective_date=date(2025, 6, 1),
        new_compensation=Decimal("50000"),
        merit_percentage=rate,
    )
    assert type(event.payload.merit_percentage) is Decimal
    assert event.payload.merit_percentage.as_tuple().exponent == -4


@PROPERTY_SETTINGS
@given(balance=SIGNED_AMOUNTS)
def test_decimal_discipline_vesting_balance_sign_is_unconstrained(
    balance: Decimal,
) -> None:
    """Vesting balance values are quantized without adding a sign rule."""
    event = CASE_BY_NAME["vesting"].spec.factory(
        employee_id="EMP001",
        scenario_id="SCENARIO",
        plan_design_id="DESIGN",
        plan_id="PLAN",
        vested_percentage=Decimal("0.5000"),
        source_balances_vested={"employer_match": balance},
        vesting_schedule_type="graded",
        service_computation_date=date(2025, 12, 31),
        service_credited_hours=1000,
        service_period_end_date=date(2025, 12, 31),
    )
    normalized = event.payload.source_balances_vested["employer_match"]
    assert type(normalized) is Decimal
    assert normalized.as_tuple().exponent == -6


_CONSTRAINED_DECIMAL_FIELDS = (
    (CASE_BY_NAME["enrollment"], "pre_tax_contribution_rate", True),
    (CASE_BY_NAME["enrollment"], "roth_contribution_rate", True),
    (CASE_BY_NAME["enrollment"], "after_tax_contribution_rate", True),
    (CASE_BY_NAME["contribution"], "amount", False),
    (CASE_BY_NAME["contribution"], "ytd_amount", False),
    (CASE_BY_NAME["vesting"], "vested_percentage", True),
    (CASE_BY_NAME["forfeiture"], "amount", False),
    (CASE_BY_NAME["forfeiture"], "vested_percentage", True),
    (CASE_BY_NAME["hce_status"], "ytd_compensation", False),
    (CASE_BY_NAME["hce_status"], "annualized_compensation", False),
    (CASE_BY_NAME["hce_status"], "hce_threshold", False),
)


@pytest.mark.parametrize(
    ("case", "field", "is_rate"),
    _CONSTRAINED_DECIMAL_FIELDS,
    ids=lambda value: value.spec.name if isinstance(value, EventFactoryCase) else None,
)
@PROPERTY_SETTINGS
@given(data=st.data())
def test_decimal_discipline_constrained_overprecision_rejected(
    case: EventFactoryCase,
    field: str,
    is_rate: bool,
    data: st.DataObject,
) -> None:
    """Fields with decimal_places constraints reject nonzero excess scale."""
    generated = data.draw(case.arguments, label=case.spec.name)
    arguments = dict(generated.arguments)
    strategy = CONSTRAINED_OVERSCALE_RATES if is_rate else CONSTRAINED_OVERSCALE_AMOUNTS
    arguments[field] = data.draw(strategy, label=field)
    with pytest.raises(ValidationError):
        case.spec.factory(**arguments)


@pytest.mark.parametrize(
    "case",
    tuple(case for case in EVENT_FACTORY_CASES if case.spec.rate_fields),
    ids=lambda case: case.spec.name,
)
@PROPERTY_SETTINGS
@given(boundary=RATE_BOUNDARIES, data=st.data())
def test_rate_boundary_is_inclusive(
    case: EventFactoryCase,
    boundary: Decimal,
    data: st.DataObject,
) -> None:
    """Every in-scope rate field accepts both zero and one."""
    generated = data.draw(case.arguments, label=case.spec.name)
    arguments = dict(generated.arguments)
    for field in case.spec.rate_fields:
        arguments[field] = boundary
    payload = case.spec.factory(**arguments).payload
    for field in case.spec.rate_fields:
        assert getattr(payload, field) == boundary.quantize(Decimal("0.0001"))


@pytest.mark.parametrize(
    "case",
    EVENT_FACTORY_CASES,
    ids=lambda case: case.spec.name,
)
@PROPERTY_SETTINGS
@given(data=st.data())
def test_effective_date_within_simulation_year(
    case: EventFactoryCase,
    data: st.DataObject,
) -> None:
    """Generated contextual dates stay in-year and map to the envelope."""
    generated = data.draw(case.arguments, label=case.spec.name)
    event = case.spec.factory(**generated.arguments)
    assert event.effective_date == generated.expected_effective_date
    assert event.effective_date.year == generated.simulation_year


@PROPERTY_SETTINGS
@given(effective_date=YEAR_BOUNDARY_DATES)
def test_effective_date_year_boundaries(effective_date: date) -> None:
    """January 1 and December 31 are accepted effective dates."""
    event = _hire_with_date(effective_date)
    assert event.effective_date == effective_date


@PROPERTY_SETTINGS
@given(effective_date=LEAP_DAYS)
def test_effective_date_leap_day(effective_date: date) -> None:
    """Leap-day effective dates retain their calendar value."""
    event = _hire_with_date(effective_date)
    assert event.effective_date == effective_date


def _hire_with_date(effective_date: date) -> SimulationEvent:
    return WorkforceEventFactory.create_hire_event(
        employee_id="EMP001",
        scenario_id="SCENARIO",
        plan_design_id="DESIGN",
        hire_date=effective_date,
        department="Engineering",
        job_level=1,
        annual_compensation=Decimal("50000"),
    )


@PROPERTY_SETTINGS
@given(pair=EMPLOYEE_LIFECYCLE_PAIRS)
def test_lifecycle_ordering(pair: EmployeeLifecyclePair) -> None:
    """Generated employee lifecycles preserve hire <= termination ordering."""
    hire = WorkforceEventFactory.create_hire_event(**pair.hire_arguments)
    termination = WorkforceEventFactory.create_termination_event(
        **pair.termination_arguments
    )
    assert hire.employee_id == termination.employee_id
    assert hire.effective_date == pair.hire_date
    assert termination.effective_date == pair.termination_date
    assert hire.effective_date <= termination.effective_date


InvalidMutationCase = tuple[EventFactoryCase, str, SearchStrategy[Any], str]


def _invalid_mutation_cases() -> tuple[InvalidMutationCase, ...]:
    cases: list[InvalidMutationCase] = []
    for case in EVENT_FACTORY_CASES:
        cases.append((case, "employee_id", WHITESPACE_ONLY_IDS, "empty_employee_id"))

    positive_fields = {
        "hire": ("annual_compensation",),
        "promotion": ("new_annual_compensation",),
        "merit": ("new_compensation",),
        "contribution": ("amount",),
        "forfeiture": ("amount",),
        "hce_status": ("hce_threshold",),
    }
    nonnegative_fields = {
        "contribution": ("ytd_amount",),
        "hce_status": ("ytd_compensation", "annualized_compensation"),
    }
    for name, fields in positive_fields.items():
        for field in fields:
            cases.append(
                (CASE_BY_NAME[name], field, NONPOSITIVE_AMOUNTS, "nonpositive_amount")
            )
    for name, fields in nonnegative_fields.items():
        for field in fields:
            cases.append(
                (CASE_BY_NAME[name], field, NEGATIVE_AMOUNTS, "negative_amount")
            )
    for name, field in (
        ("hire", "annual_compensation"),
        ("promotion", "new_annual_compensation"),
        ("merit", "new_compensation"),
    ):
        cases.append(
            (
                CASE_BY_NAME[name],
                field,
                SUBQUANTUM_POSITIVE_AMOUNTS,
                "subquantum_compensation",
            )
        )
    for case in EVENT_FACTORY_CASES:
        for field in case.spec.rate_fields:
            cases.append((case, field, INVALID_RATES, "out_of_range_rate"))
    return tuple(cases)


_INVALID_MUTATION_CASES = _invalid_mutation_cases()


@pytest.mark.parametrize(
    ("case", "field", "invalid_values", "category"),
    _INVALID_MUTATION_CASES,
    ids=(
        f"{case.spec.name}-{field}-{category}"
        for case, field, _strategy, category in _INVALID_MUTATION_CASES
    ),
)
@PROPERTY_SETTINGS
@given(data=st.data())
def test_invalid_input_rejected(
    case: EventFactoryCase,
    field: str,
    invalid_values: SearchStrategy[Any],
    category: str,
    data: st.DataObject,
) -> None:
    """Malformed values raise ValidationError through the public factory."""
    invalid = data.draw(
        invalid_event_inputs(case, field, invalid_values, category),
        label=f"{case.spec.name}-{field}-{category}",
    )
    with pytest.raises(ValidationError):
        invalid.case.spec.factory(**invalid.arguments)


@pytest.mark.parametrize(
    "case",
    EVENT_FACTORY_CASES,
    ids=lambda case: case.spec.name,
)
@PROPERTY_SETTINGS
@given(data=st.data())
def test_json_contract_and_json_round_trip(
    case: EventFactoryCase,
    data: st.DataObject,
) -> None:
    """JSON-mode output retains exact audit keys, types, and values."""
    generated = data.draw(case.arguments, label=case.spec.name)
    event = case.spec.factory(**generated.arguments)
    wire = event.model_dump(mode="json")

    assert frozenset(wire) == frozenset(ENVELOPE_JSON_TYPES)
    for field, expected_types in ENVELOPE_JSON_TYPES.items():
        assert type(wire[field]) in expected_types  # noqa: E721

    payload = wire["payload"]
    assert type(payload) is dict  # noqa: E721
    assert frozenset(payload) == case.spec.payload_keys
    for field, expected_types in case.spec.payload_json_types.items():
        assert type(payload[field]) in expected_types  # noqa: E721

    for field in case.spec.amount_fields:
        assert Decimal(payload[field]).as_tuple().exponent == -6
    for field in case.spec.rate_fields:
        assert Decimal(payload[field]).as_tuple().exponent == -4
    for field in case.spec.nested_amount_fields:
        for value in payload[field].values():
            assert type(value) is str  # noqa: E721
            assert Decimal(value).as_tuple().exponent == -6

    UUID(wire["event_id"])
    date.fromisoformat(wire["effective_date"])
    datetime.fromisoformat(wire["created_at"].replace("Z", "+00:00"))
    encoded = json.dumps(wire, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert SimulationEvent.model_validate(decoded) == event
