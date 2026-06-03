"""Census schema definition — canonical field list consumed by stg_census_data.sql.

This module is the single source of truth for what column names the simulation
engine accepts in a census parquet file. Nothing here should be changed without
a matching update to dbt/models/staging/stg_census_data.sql.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CensusFieldDefinition:
    field_name: str
    required: bool
    data_type: str  # "string" | "date" | "decimal" | "boolean"
    description: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


FIELDS: tuple[CensusFieldDefinition, ...] = (
    CensusFieldDefinition(
        field_name="employee_id",
        required=True,
        data_type="string",
        description="Unique employee identifier — the primary key used across all simulation events",
        aliases=("empid", "emp_id", "id", "employeeid", "employee_number", "emp_no", "empno",
                 "employee_no", "staff_id", "staffid", "worker_id", "workerid"),
    ),
    CensusFieldDefinition(
        field_name="employee_birth_date",
        required=True,
        data_type="date",
        description="Date of birth — used to calculate age bands and age-based simulation parameters",
        aliases=("dob", "date_of_birth", "birthdate", "birth_date", "dateofbirth",
                 "birth", "bdate", "born"),
    ),
    CensusFieldDefinition(
        field_name="employee_hire_date",
        required=True,
        data_type="date",
        description="Original hire date — used to calculate service tenure and plan eligibility",
        aliases=("hire_date", "hiredate", "date_of_hire", "dateofhire", "start_date",
                 "startdate", "hire", "employment_date", "employmentdate", "date_hired"),
    ),
    CensusFieldDefinition(
        field_name="employee_gross_compensation",
        required=True,
        data_type="decimal",
        description=(
            "Annual salary rate (not prorated) — used to calculate compensation growth "
            "and DC plan contributions"
        ),
        aliases=("salary", "annual_salary", "base_pay", "gross_comp", "compensation",
                 "base_salary", "annualsalary", "basepay", "grosscomp", "annual_compensation",
                 "annualcompensation", "base_compensation", "pay", "wages", "annualpay",
                 "annual_pay", "total_comp", "totalcomp"),
    ),
    CensusFieldDefinition(
        field_name="active",
        required=True,
        data_type="boolean",
        description="Whether the employee is currently employed — filters active workforce for simulation",
        aliases=("status", "is_active", "isactive", "employment_status", "employmentstatus",
                 "employed", "current", "active_flag", "activeflag"),
    ),
    CensusFieldDefinition(
        field_name="employee_ssn",
        required=False,
        data_type="string",
        description=(
            "Synthetic SSN-style identifier (e.g., SSN-00000001) — not a real SSN; "
            "used as an alternative unique identifier"
        ),
        aliases=("ssn", "social_security", "ssn_id", "socialsecurity"),
    ),
    CensusFieldDefinition(
        field_name="employee_termination_date",
        required=False,
        data_type="date",
        description="Termination date for separated employees — null for active employees",
        aliases=("term_date", "termination_date", "separation_date", "end_date",
                 "termdate", "separationdate", "enddate", "exit_date", "exitdate",
                 "date_terminated", "dateterminated"),
    ),
    CensusFieldDefinition(
        field_name="employee_capped_compensation",
        required=False,
        data_type="decimal",
        description=(
            "IRS 401(a)(17) capped compensation — compensation subject to annual IRS limit; "
            "defaults to gross compensation if not provided"
        ),
        aliases=("capped_comp", "cappedcomp", "415_limit", "irs_cap", "plan_year_compensation",
                 "capped_compensation"),
    ),
    CensusFieldDefinition(
        field_name="employee_deferral_rate",
        required=False,
        data_type="decimal",
        description="Current deferral rate as a decimal (0.00–1.00, e.g., 0.06 = 6%)",
        aliases=("deferral_rate", "deferralrate", "deferral_pct", "contribution_rate",
                 "contributionrate", "deferral", "deferral_percent"),
    ),
    CensusFieldDefinition(
        field_name="employee_contribution",
        required=False,
        data_type="decimal",
        description="Total employee contribution dollar amount for the plan year",
        aliases=("total_ee_contribution", "employee_contribution", "ee_contribution",
                 "eecontribution", "total_contribution", "totalcontribution"),
    ),
    CensusFieldDefinition(
        field_name="pre_tax_contribution",
        required=False,
        data_type="decimal",
        description="Pre-tax (traditional) 401(k) deferral amount",
        aliases=("pre_tax", "pretax", "traditional_401k", "traditional401k",
                 "pretax_contribution", "pre_tax_deferral"),
    ),
    CensusFieldDefinition(
        field_name="roth_contribution",
        required=False,
        data_type="decimal",
        description="Roth 401(k) after-tax deferral amount",
        aliases=("roth", "roth_401k", "roth401k", "roth_deferral"),
    ),
    CensusFieldDefinition(
        field_name="after_tax_contribution",
        required=False,
        data_type="decimal",
        description="After-tax (non-Roth) contribution amount",
        aliases=("after_tax", "aftertax", "after_tax_voluntary", "aftertaxcontribution"),
    ),
    CensusFieldDefinition(
        field_name="employer_core_contribution",
        required=False,
        data_type="decimal",
        description="Employer non-elective (core/profit-sharing) contribution amount",
        aliases=("er_core", "ercore", "non_elective", "nonelective", "employer_core",
                 "profit_sharing", "profitsharing", "core_contribution"),
    ),
    CensusFieldDefinition(
        field_name="employer_match_contribution",
        required=False,
        data_type="decimal",
        description="Employer matching contribution amount",
        aliases=("er_match", "ermatch", "employer_match", "matching", "match_contribution",
                 "matchcontribution", "employer_matching"),
    ),
    CensusFieldDefinition(
        field_name="eligibility_entry_date",
        required=False,
        data_type="date",
        description=(
            "Override for plan eligibility entry date — if provided, used instead of "
            "the calculated hire-date + waiting-period date"
        ),
        aliases=("entry_date", "entrydate", "eligibility_date", "eligibilitydate",
                 "plan_entry", "planentry", "eligibility_entry"),
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
