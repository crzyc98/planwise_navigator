"""Census schema definition — canonical field list consumed by stg_census_data.sql.

This module is the single source of truth for what column names the simulation
engine accepts in a census parquet file. Nothing here should be changed without
a matching update to dbt/models/staging/stg_census_data.sql.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import re

from planalign_orchestrator.census_hourly_rate import hourly_rate_bounds

BOOLEAN_TRUE_ALIASES = frozenset(
    {
        "y",
        "yes",
        "true",
        "t",
        "1",
        "1.0",
        "active",
        "enrolled",
        "eligible",
        "employed",
    }
)
BOOLEAN_FALSE_ALIASES = frozenset(
    {
        "n",
        "no",
        "false",
        "0",
        "0.0",
        "inactive",
        "terminated",
        "separated",
        "ineligible",
    }
)


def active_filter_sql(columns: Collection[str]) -> str:
    """Include missing/NULL active values and the shared true aliases."""
    if "active" not in columns:
        return "1=1"
    aliases = ", ".join(f"'{alias}'" for alias in sorted(BOOLEAN_TRUE_ALIASES))
    return f"(active IS NULL OR LOWER(TRIM(CAST(active AS VARCHAR))) IN ({aliases}))"


CENSUS_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%Y%m%d",
)

# Both DuckDB uploads and mapped pandas imports use these same validation rules.
GROUPED_NUMBER_PATTERN = r"-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
GROUPED_NUMBER_RE = re.compile(rf"^{GROUPED_NUMBER_PATTERN}$")


def clean_census_number(value: str) -> str | None:
    """Remove supported currency decoration only after validating comma groups."""
    token = value.strip().replace("$", "").replace("€", "").replace("£", "")
    token = "".join(token.split())
    if token.startswith("(") and token.endswith(")"):
        token = f"-{token[1:-1]}"
    if not GROUPED_NUMBER_RE.fullmatch(token):
        return None
    return token.replace(",", "")


def matching_census_date_formats(values: list[str]) -> tuple[str, ...]:
    """Find formats that parse every nonblank value in one column."""
    nonblank = [value.strip() for value in values if value and value.strip()]
    return tuple(
        fmt
        for fmt in CENSUS_DATE_FORMATS
        if all(_parse_census_date(value, fmt) is not None for value in nonblank)
    )


def _parse_census_date(value: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(value, fmt)
    except ValueError:
        return None


def census_date_order_is_ambiguous(values: list[str], formats: tuple[str, ...]) -> bool:
    """Distinguish different spellings of one date from conflicting date orders."""
    return any(
        _parse_census_date(value.strip(), formats[0])
        != _parse_census_date(value.strip(), fmt)
        for value in values
        if value and value.strip()
        for fmt in formats[1:]
    )


# Optional-column groups for the Studio census guide, in display order. A field
# whose group is not listed here (or that sets none) shows under "other".
CENSUS_FIELD_GROUPS: tuple[tuple[str, str], ...] = (
    ("status", "Identity and status"),
    ("pay", "Pay"),
    ("participation", "Plan participation and contributions"),
    ("eligibility", "Eligibility"),
    ("hours", "Hours"),
    ("other", "Other columns"),
)

_RATE_MIN, _RATE_MAX = hourly_rate_bounds()
_RATE_CHECK = (
    f"A rate below ${_RATE_MIN:g} or above ${_RATE_MAX:g} an hour is flagged at "
    "import, and the person is kept with no rate."
)

_EXAMPLE_BY_TYPE = {
    "string": "EXAMPLE",
    "date": "2020-01-15",
    "decimal": "0",
    "boolean": "true",
}


@dataclass(frozen=True)
class CensusFieldDefinition:
    """One census column.

    ``label``, ``group``, ``example`` and ``when_missing`` only feed the Studio
    census guide and template; they never change ingestion. They default so a
    field added without them still renders (label from the name, group
    "other", an example by type, and no when-missing sentence).
    """

    field_name: str
    required: bool
    data_type: str  # "string" | "date" | "decimal" | "boolean"
    description: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    label: str = ""
    group: str = "other"
    # None means "use the type's example"; "" means the template leaves it blank.
    example: Optional[str] = None
    when_missing: str = ""

    @property
    def display_label(self) -> str:
        return self.label or self.field_name.replace("_", " ").capitalize()

    @property
    def example_value(self) -> str:
        if self.example is not None:
            return self.example
        return _EXAMPLE_BY_TYPE.get(self.data_type, "")


FIELDS: tuple[CensusFieldDefinition, ...] = (
    CensusFieldDefinition(
        field_name="employee_id",
        required=True,
        data_type="string",
        description=(
            "A unique ID for each employee. Studio uses it to follow each person from "
            "year to year."
        ),
        aliases=(
            "empid",
            "emp_id",
            "id",
            "employeeid",
            "employee_number",
            "emp_no",
            "empno",
            "employee_no",
            "staff_id",
            "staffid",
            "worker_id",
            "workerid",
        ),
        label="Employee ID",
        example="SAMPLE-0001",
        when_missing="Every row needs one. The import stops if any row is blank.",
    ),
    CensusFieldDefinition(
        field_name="employee_birth_date",
        required=True,
        data_type="date",
        description="Date of birth. Used for age, age bands and age-based plan rules.",
        aliases=(
            "dob",
            "date_of_birth",
            "birthdate",
            "birth_date",
            "dateofbirth",
            "birth",
            "bdate",
            "born",
        ),
        label="Birth date",
        example="1985-04-12",
    ),
    CensusFieldDefinition(
        field_name="employee_hire_date",
        required=True,
        data_type="date",
        description=(
            "Original hire date. Used for length of service and plan eligibility."
        ),
        aliases=(
            "hire_date",
            "hiredate",
            "date_of_hire",
            "dateofhire",
            "start_date",
            "startdate",
            "hire",
            "employment_date",
            "employmentdate",
            "date_hired",
        ),
        label="Hire date",
        example="2015-06-01",
    ),
    CensusFieldDefinition(
        field_name="employee_gross_compensation",
        required=True,
        data_type="decimal",
        description=(
            "Pay earned in the census year, as the sponsor reports it. People hired or "
            "leaving during the year show part-year pay; Studio estimates a yearly "
            "rate for new hires."
        ),
        aliases=(
            "salary",
            "annual_salary",
            "base_pay",
            "gross_comp",
            "compensation",
            "base_salary",
            "annualsalary",
            "basepay",
            "grosscomp",
            "annual_compensation",
            "annualcompensation",
            "base_compensation",
            "pay",
            "wages",
            "annualpay",
            "annual_pay",
            "total_comp",
            "totalcomp",
        ),
        label="Pay",
        example="72000.00",
    ),
    CensusFieldDefinition(
        field_name="active",
        required=True,
        data_type="boolean",
        description="Whether the person still works there: yes or no.",
        aliases=(
            "status",
            "is_active",
            "isactive",
            "employment_status",
            "employmentstatus",
            "employed",
            "current",
            "active_flag",
            "activeflag",
        ),
        label="Active",
        example="true",
        when_missing=(
            "Census Analysis uses it to count current employees. The simulation starts "
            "from everyone without a termination date, so give leavers a termination "
            "date too."
        ),
    ),
    CensusFieldDefinition(
        field_name="employee_ssn",
        required=False,
        data_type="string",
        description=(
            "A second made-up ID in SSN style. Never a real Social Security number."
        ),
        aliases=("ssn", "social_security", "ssn_id", "socialsecurity"),
        label="SSN-style ID",
        group="status",
        example="SSN-00000001",
        when_missing=(
            "Leave it out: Studio makes a placeholder from the employee ID. If you "
            "send one, Studio stores it as given, so it must not be a real SSN."
        ),
    ),
    CensusFieldDefinition(
        field_name="employee_termination_date",
        required=False,
        data_type="date",
        description="Date the person left. Leave blank for current employees.",
        aliases=(
            "term_date",
            "termination_date",
            "separation_date",
            "end_date",
            "termdate",
            "separationdate",
            "enddate",
            "exit_date",
            "exitdate",
            "date_terminated",
            "dateterminated",
        ),
        label="Termination date",
        group="status",
        example="",
        when_missing=(
            "Without it, every row starts the simulation as a current employee, even "
            "rows marked inactive. With it, people who left are kept out of the "
            "starting workforce."
        ),
    ),
    CensusFieldDefinition(
        field_name="employee_capped_compensation",
        required=False,
        data_type="decimal",
        description="Pay after the IRS annual pay limit.",
        aliases=(
            "capped_comp",
            "cappedcomp",
            "415_limit",
            "irs_cap",
            "plan_year_compensation",
            "capped_compensation",
        ),
        label="Capped pay",
        group="pay",
        example="72000.00",
        when_missing=(
            "Not used today. Studio applies the IRS pay limit itself, so leaving this "
            "out changes nothing."
        ),
    ),
    CensusFieldDefinition(
        field_name="employee_deferral_rate",
        required=False,
        data_type="decimal",
        description="Share of pay the employee saves, as a decimal: 0.06 means 6%.",
        aliases=(
            "deferral_rate",
            "deferralrate",
            "deferral_pct",
            "contribution_rate",
            "contributionrate",
            "deferral",
            "deferral_percent",
        ),
        label="Deferral rate",
        group="participation",
        example="0.06",
        when_missing=(
            "Without it, everyone starts at 0% and not enrolled, so savers come only "
            "from auto-enrollment and modeled sign-ups. With it, current savers start "
            "at their real rate."
        ),
    ),
    CensusFieldDefinition(
        field_name="employee_contribution",
        required=False,
        data_type="decimal",
        description="Total dollars the employee contributed in the plan year.",
        aliases=(
            "total_ee_contribution",
            "employee_contribution",
            "ee_contribution",
            "eecontribution",
            "total_contribution",
            "totalcontribution",
        ),
        label="Employee contributions",
        group="participation",
        example="4320.00",
        when_missing=(
            "Not used today. Studio works out contributions from pay and the deferral "
            "rate, so leaving this out changes nothing."
        ),
    ),
    CensusFieldDefinition(
        field_name="pre_tax_contribution",
        required=False,
        data_type="decimal",
        description="Pre-tax (traditional) 401(k) dollars for the plan year.",
        aliases=(
            "pre_tax",
            "pretax",
            "traditional_401k",
            "traditional401k",
            "pretax_contribution",
            "pre_tax_deferral",
        ),
        label="Pre-tax contributions",
        group="participation",
        example="3000.00",
        when_missing=(
            "Not used today. Studio works out contributions from pay and the deferral "
            "rate, so leaving this out changes nothing."
        ),
    ),
    CensusFieldDefinition(
        field_name="roth_contribution",
        required=False,
        data_type="decimal",
        description="Roth 401(k) dollars for the plan year.",
        aliases=("roth", "roth_401k", "roth401k", "roth_deferral"),
        label="Roth contributions",
        group="participation",
        example="1320.00",
        when_missing=(
            "Not used today. Studio works out contributions from pay and the deferral "
            "rate, so leaving this out changes nothing."
        ),
    ),
    CensusFieldDefinition(
        field_name="after_tax_contribution",
        required=False,
        data_type="decimal",
        description="After-tax (non-Roth) dollars for the plan year.",
        aliases=(
            "after_tax",
            "aftertax",
            "after_tax_voluntary",
            "aftertaxcontribution",
        ),
        label="After-tax contributions",
        group="participation",
        example="0.00",
        when_missing=(
            "Not used today. Studio works out contributions from pay and the deferral "
            "rate, so leaving this out changes nothing."
        ),
    ),
    CensusFieldDefinition(
        field_name="employer_core_contribution",
        required=False,
        data_type="decimal",
        description=(
            "Employer non-elective (core or profit-sharing) dollars for the plan year."
        ),
        aliases=(
            "er_core",
            "ercore",
            "non_elective",
            "nonelective",
            "employer_core",
            "profit_sharing",
            "profitsharing",
            "core_contribution",
        ),
        label="Employer core dollars",
        group="participation",
        example="2160.00",
        when_missing=(
            "The simulation works out core from the plan rules. With this column, "
            "Census Analysis and the census tie-out show the census year's core "
            "dollars beside the model's."
        ),
    ),
    CensusFieldDefinition(
        field_name="employer_match_contribution",
        required=False,
        data_type="decimal",
        description="Employer matching dollars for the plan year.",
        aliases=(
            "er_match",
            "ermatch",
            "employer_match",
            "matching",
            "match_contribution",
            "matchcontribution",
            "employer_matching",
        ),
        label="Employer match dollars",
        group="participation",
        example="2880.00",
        when_missing=(
            "The simulation works out match from the plan rules. With this column, "
            "Census Analysis and the census tie-out show the census year's match "
            "dollars beside the model's."
        ),
    ),
    CensusFieldDefinition(
        field_name="eligibility_entry_date",
        required=False,
        data_type="date",
        description="Date the employee entered, or will enter, the plan.",
        aliases=(
            "entry_date",
            "entrydate",
            "eligibility_date",
            "eligibilitydate",
            "plan_entry",
            "planentry",
            "eligibility_entry",
        ),
        label="Plan entry date",
        group="eligibility",
        example="2015-07-01",
        when_missing=(
            "The simulation works out eligibility from hire date and plan rules, not "
            "this date. With it, Census Analysis and the census tie-out count who is "
            "eligible; without it, every active employee counts."
        ),
    ),
    # Hourly pay (#1230). One per person is enough; when several are filled the
    # first of hourly_rate, hours_worked, scheduled_hours_per_week wins.
    CensusFieldDefinition(
        field_name="hourly_rate",
        required=False,
        data_type="decimal",
        description=(
            "Base pay per hour in dollars, for hourly employees. Leave blank for "
            "anyone who is not hourly."
        ),
        aliases=("hourly_pay_rate", "hourly_wage", "rate_per_hour"),
        label="Hourly rate",
        group="hours",
        example="34.62",
        when_missing=(
            "A minimum wage change needs an hourly rate from this column, hours "
            "worked or weekly hours. Someone with all three blank has no rate, so a "
            "minimum wage leaves their pay alone; if nobody has a rate, a run with "
            "a minimum wage stops. This column is the best source, because overtime "
            "and bonuses don't change it. " + _RATE_CHECK
        ),
    ),
    CensusFieldDefinition(
        field_name="hours_worked",
        required=False,
        data_type="decimal",
        description="All paid hours in the census year, overtime included.",
        aliases=("annual_hours_worked", "paid_hours", "hours_paid"),
        label="Hours worked",
        group="hours",
        example="2080",
        when_missing=(
            "Used when hourly rate is blank: the hourly rate is the year's pay "
            "divided by these hours. Overtime and bonuses push that rate up, so send "
            "hourly rate when you can. Someone with all three hours columns blank "
            "has no hourly rate."
        ),
    ),
    CensusFieldDefinition(
        field_name="scheduled_hours_per_week",
        required=False,
        data_type="decimal",
        description="Usual scheduled hours in a week.",
        aliases=("hours_per_week", "scheduled_hours", "weekly_hours"),
        label="Weekly hours",
        group="hours",
        example="40",
        when_missing=(
            "Without it, every census employee counts as working 40 hours a week "
            "for the employer match and core hours rule (often 1,000 a year), and "
            "Studio can't suggest a part-time share for new hires. It is also the "
            "last source of an hourly rate: yearly pay divided by (weekly hours x 52)."
        ),
    ),
)

CANONICAL_NAMES: frozenset[str] = frozenset(f.field_name for f in FIELDS)
_FIELD_INDEX: dict[str, CensusFieldDefinition] = {f.field_name: f for f in FIELDS}


def is_canonical(name: str) -> bool:
    return name in CANONICAL_NAMES


def get_required_fields() -> list[str]:
    return [f.field_name for f in FIELDS if f.required]


def get_field(name: str) -> Optional[CensusFieldDefinition]:
    return _FIELD_INDEX.get(name)
