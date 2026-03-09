"""Centralized string constants for Fidelity PlanAlign Engine.

This module defines constants for strings that are used across multiple files
to eliminate duplication and ensure consistency. Organized by category.
"""


# =============================================================================
# Database & Table Names
# =============================================================================

DATABASE_FILENAME = "simulation.duckdb"

# Fact tables (marts layer)
TABLE_FCT_YEARLY_EVENTS = "fct_yearly_events"
TABLE_FCT_WORKFORCE_SNAPSHOT = "fct_workforce_snapshot"
TABLE_FCT_DC_PLAN_SUMMARY = "fct_dc_plan_summary"
TABLE_FCT_DC_CONTRIBUTIONS = "fct_dc_contributions"
TABLE_FCT_EMPLOYER_COST_SUMMARY = "fct_employer_cost_summary"

# Dimension tables
TABLE_DIM_EMPLOYEES = "dim_employees"

# Staging tables
TABLE_STG_CENSUS = "stg_census"


# =============================================================================
# Column Names - Core Entity Identifiers
# =============================================================================

COL_EMPLOYEE_ID = "employee_id"
COL_SCENARIO_ID = "scenario_id"
COL_PLAN_DESIGN_ID = "plan_design_id"
COL_SIMULATION_YEAR = "simulation_year"
COL_EVENT_TYPE = "event_type"
COL_EFFECTIVE_DATE = "effective_date"
COL_CREATED_AT = "created_at"
COL_TIMESTAMP = "timestamp"

# Workforce columns
COL_ANNUAL_COMPENSATION = "annual_compensation"
COL_JOB_LEVEL = "job_level"
COL_DEPARTMENT = "department"
COL_HIRE_DATE = "hire_date"
COL_BIRTH_DATE = "birth_date"
COL_TERMINATION_DATE = "termination_date"
COL_IS_ACTIVE = "is_active"
COL_CURRENT_AGE = "current_age"
COL_CURRENT_TENURE = "current_tenure"
COL_AGE_BAND = "age_band"
COL_TENURE_BAND = "tenure_band"

# DC Plan columns
COL_DEFERRAL_RATE = "deferral_rate"
COL_MATCH_RATE = "match_rate"
COL_ENROLLMENT_DATE = "enrollment_date"
COL_VESTING_PERCENTAGE = "vesting_percentage"
COL_EMPLOYEE_CONTRIBUTION = "employee_contribution"
COL_EMPLOYER_MATCH = "employer_match"
COL_EMPLOYER_CORE = "employer_core"


# =============================================================================
# Event Types
# =============================================================================

EVENT_HIRE = "hire"
EVENT_TERMINATION = "termination"
EVENT_PROMOTION = "promotion"
EVENT_MERIT = "merit"
EVENT_ENROLLMENT = "enrollment"
EVENT_SABBATICAL = "sabbatical"
EVENT_DEFERRAL_ESCALATION = "deferral_escalation"

# Uppercase event types (used in event payloads / fct_yearly_events)
EVENT_TYPE_HIRE = "HIRE"
EVENT_TYPE_TERMINATION = "TERMINATION"
EVENT_TYPE_PROMOTION = "PROMOTION"
EVENT_TYPE_RAISE = "RAISE"
EVENT_TYPE_MERIT = "MERIT"
EVENT_TYPE_ENROLLMENT = "ENROLLMENT"
EVENT_TYPE_BENEFIT_ENROLLMENT = "BENEFIT_ENROLLMENT"
EVENT_TYPE_DC_PLAN_ELIGIBILITY = "DC_PLAN_ELIGIBILITY"
EVENT_TYPE_DC_PLAN_ENROLLMENT = "DC_PLAN_ENROLLMENT"
EVENT_TYPE_DC_PLAN_CONTRIBUTION = "DC_PLAN_CONTRIBUTION"
EVENT_TYPE_DC_PLAN_VESTING = "DC_PLAN_VESTING"
EVENT_TYPE_FORFEITURE = "FORFEITURE"
EVENT_TYPE_HCE_STATUS = "HCE_STATUS"
EVENT_TYPE_DEFERRAL_ESCALATION = "DEFERRAL_ESCALATION"
EVENT_TYPE_MATCH_RESPONSE = "MATCH_RESPONSE"


# =============================================================================
# dbt Model Names (Intermediate Layer)
# =============================================================================

MODEL_INT_BASELINE_WORKFORCE = "int_baseline_workforce"
MODEL_INT_ACTIVE_EMPLOYEES_PREV_YEAR = "int_active_employees_prev_year_snapshot"
MODEL_INT_EMPLOYEE_COMPENSATION = "int_employee_compensation_by_year"
MODEL_INT_WORKFORCE_NEEDS = "int_workforce_needs"
MODEL_INT_NEW_HIRE_COMPENSATION = "int_new_hire_compensation_staging"
MODEL_INT_ENROLLMENT_STATE_ACCUMULATOR = "int_enrollment_state_accumulator"
MODEL_INT_DEFERRAL_RATE_STATE_ACCUMULATOR = "int_deferral_rate_state_accumulator"
MODEL_INT_TERMINATION_EVENTS = "int_termination_events"
MODEL_INT_HIRE_EVENTS = "int_hire_events"
MODEL_INT_PROMOTION_EVENTS = "int_promotion_events"
MODEL_INT_MERIT_EVENTS = "int_merit_events"
MODEL_INT_ENROLLMENT_EVENTS = "int_enrollment_events"
MODEL_INT_DEFERRAL_ESCALATION_EVENTS = "int_deferral_escalation_events"
MODEL_INT_MATCH_RESPONSE_EVENTS = "int_match_response_events"
MODEL_INT_DC_PLAN_CONTRIBUTIONS = "int_dc_plan_contributions"
MODEL_INT_DC_PLAN_EMPLOYER_CORE = "int_dc_plan_employer_core"
MODEL_INT_WORKFORCE_SNAPSHOT_FINAL = "int_workforce_snapshot_final"

# Marts models
MODEL_FCT_YEARLY_EVENTS = "fct_yearly_events"
MODEL_FCT_WORKFORCE_SNAPSHOT = "fct_workforce_snapshot"
MODEL_FCT_DC_PLAN_SUMMARY = "fct_dc_plan_summary"


# =============================================================================
# Validation Keys
# =============================================================================

KEY_ERRORS = "errors"
KEY_WARNINGS = "warnings"
KEY_STATUS = "status"
KEY_MESSAGE = "message"
KEY_SUCCESS = "success"
KEY_RESULTS = "results"


# =============================================================================
# Status Strings
# =============================================================================

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_PENDING = "pending"
STATUS_CANCELLED = "cancelled"


# =============================================================================
# Registry Table Names
# =============================================================================

REGISTRY_ENROLLMENT = "enrollment_registry"
REGISTRY_DEFERRAL_ESCALATION = "deferral_escalation_registry"
