# Fidelity PlanAlign Engine - Legal Documentation

**Document Version**: 1.0
**Last Updated**: 2025-01-24
**System Version**: 1.0.0 (Foundation)
**Prepared For**: Legal Review and Compliance

---

## Executive Summary

Fidelity PlanAlign Engine is a workforce simulation and financial modeling platform designed to project multi-year workforce costs, retirement plan participation, and organizational headcount scenarios. The system uses event-sourced architecture to maintain complete audit trails and ensure reproducibility of all financial projections.

---

## 1. Data Inputs

### 1.1 Primary Input Files (CSV Format)

All input data is provided via CSV files in the `/data/` directory:

| Input File | Description | Data Elements | Source |
|:-----------|:------------|:--------------|:-------|
| `employees.csv` | Current workforce roster | Employee ID, hire date, department, job level, compensation, employment status | HR Systems |
| `departments.csv` | Organizational structure | Department ID, department name, cost center, reporting hierarchy | Finance/HR Systems |
| `job_levels.csv` | Job classification system | Level ID, level name, salary band, grade | HR Compensation System |
| `scenario_config.csv` | Scenario parameters | Scenario ID, name, description, start year, end year | Business Planning Team |
| `plan_design_config.csv` | DC plan configurations | Plan ID, plan name, eligibility rules, matching formulas, vesting schedules | Benefits Administration |
| `compensation_assumptions.csv` | Salary adjustment rates | Year, COLA rate, merit increase rate, promotion increase rate | Finance Planning Team |
| `turnover_assumptions.csv` | Attrition probabilities | Job level, tenure band, voluntary/involuntary termination rate | HR Analytics |
| `hiring_assumptions.csv` | Recruitment projections | Year, department, planned hires, target level distribution | Workforce Planning Team |
| `promotion_assumptions.csv` | Advancement probabilities | Current level, target level, probability, eligibility criteria | HR Policy |

### 1.2 System Configuration Files

| Configuration File | Purpose | Format |
|:-------------------|:--------|:-------|
| `config/simulation_config.yaml` | Simulation parameters, random seeds, feature flags | YAML |
| `dbt/dbt_project.yml` | Data transformation project configuration | YAML |
| `dbt/profiles.yml` | Database connection settings | YAML |

### 1.3 Data Sensitivity Classification

- **PII (Personally Identifiable Information)**: Employee ID, hire dates, compensation data
- **Financial Data**: All compensation, contribution, and cost projection outputs
- **Business Confidential**: Turnover rates, hiring plans, organizational structure

---

## 2. Data Sources

### 2.1 External Systems (Upstream)

| System | Data Category | Integration Method | Update Frequency |
|:-------|:--------------|:-------------------|:-----------------|
| HR Information System (HRIS) | Employee demographics, job data, org structure | CSV export | Monthly/As-needed |
| Payroll System | Current compensation, historical increases | CSV export | Monthly/As-needed |
| Benefits Administration Platform | DC plan enrollment, contribution rates, vesting | CSV export | Quarterly/As-needed |
| Finance Planning System | Compensation assumptions, budget constraints | CSV export | Annually/As-needed |
| Workforce Planning Tool | Hiring plans, headcount targets | CSV export | Annually/As-needed |

### 2.2 Internal Data Stores

| Store | Technology | Purpose | Retention |
|:------|:-----------|:--------|:----------|
| `simulation.duckdb` | DuckDB 1.0.0 | Primary event store and analytical database | Permanent (project lifecycle) |
| Batch output databases | DuckDB 1.0.0 | Scenario-specific isolated databases | Permanent (archived) |
| Excel exports | XLSX | Stakeholder reporting and compliance documentation | Permanent (archived) |

---

## 3. Key Assumptions

### 3.1 Workforce Modeling Assumptions

1. **Turnover Modeling**
   - Voluntary and involuntary termination rates are independent
   - Turnover probability varies by job level and tenure
   - Historical termination patterns predict future attrition
   - Termination events are randomly sampled using hazard-based survival analysis

2. **Hiring Modeling**
   - Hiring plans represent net new headcount (not backfill)
   - New hire compensation follows current market salary bands
   - New hires are distributed across job levels per planning assumptions
   - Hire dates are uniformly distributed throughout the year

3. **Promotion Modeling**
   - Promotion eligibility requires minimum tenure in current level
   - Promotion probability varies by current and target level
   - Promotions result in compensation increases per policy
   - Employees can only be promoted one level per year

4. **Compensation Modeling**
   - COLA (Cost of Living Adjustment) applies to all active employees
   - Merit increases apply to eligible employees (performance-based proxy)
   - Promotion increases are additive to COLA/merit
   - Compensation changes are effective January 1st of each year

### 3.2 Retirement Plan (DC Plan) Assumptions

1. **Eligibility**
   - New hires become eligible based on plan-specific rules (e.g., immediate, 90 days, 1 year)
   - Eligibility is determined at hire and re-evaluated at each year-end

2. **Enrollment**
   - Auto-enrollment applies to eligible employees per plan design
   - Employees can opt-out or change deferral rates at any time (modeled annually)
   - Default deferral rates apply for auto-enrolled participants

3. **Contributions**
   - Employee deferrals are calculated as percentage of annual compensation
   - Employer match is calculated per plan formula (e.g., 100% on first 6%)
   - Contributions are annualized (single contribution per year for simplicity)
   - True-up contributions are calculated at year-end for mid-year hires

4. **Vesting**
   - Vesting schedules are plan-specific (e.g., immediate, 3-year cliff, 6-year graded)
   - Vesting percentage applies to employer contributions only
   - Forfeitures from terminated unvested participants are tracked separately

5. **Highly Compensated Employee (HCE) Status**
   - HCE determination follows IRS threshold (e.g., $150,000 compensation)
   - HCE status is evaluated annually based on prior year compensation
   - Used for compliance testing (not enforcement in simulation)

### 3.3 Technical Assumptions

1. **Event Sourcing**
   - All workforce changes are recorded as immutable events with UUID timestamps
   - Events are append-only; no updates or deletions
   - Complete workforce history can be reconstructed from event log

2. **Reproducibility**
   - Identical random seed produces identical simulation results
   - Git commit SHA is recorded for code versioning audit trail
   - All input data and configuration are versioned with outputs

3. **Data Quality**
   - Input data is assumed to be accurate and validated upstream
   - Simulation validates internal consistency (e.g., no terminations before hire)
   - Data quality tests run automatically during pipeline execution

---

## 4. Process Description

### 4.1 High-Level Workflow

```
Input Data (CSV) → Validation → Event Generation → State Accumulation → Projections → Outputs
```

### 4.2 Detailed Process Steps

#### Phase 1: Initialization
1. Load simulation configuration from YAML files
2. Validate all required input CSV files are present and schema-compliant
3. Create or connect to DuckDB database (`dbt/simulation.duckdb`)
4. Load CSV seed data into staging tables

#### Phase 2: Foundation (Year 0 / Baseline)
1. **Staging**: Clean and standardize raw input data
   - Deduplicate employee records
   - Validate data types and required fields
   - Apply business rules (e.g., active employees only)

2. **Baseline Workforce**: Establish starting workforce state
   - Identify all active employees as of simulation start date
   - Assign to scenario and plan design contexts
   - Calculate baseline compensation and demographics

#### Phase 3: Event Generation (For Each Simulation Year)
1. **Termination Events**: Model employee departures
   - Sample termination events using hazard-based probabilities
   - Generate termination events with effective dates
   - Record reason codes (voluntary/involuntary)

2. **Hiring Events**: Model new employee onboarding
   - Generate hire events per hiring plan targets
   - Assign job levels, departments, compensation per assumptions
   - Create unique employee IDs for new hires

3. **Promotion Events**: Model employee advancement
   - Identify promotion-eligible employees
   - Sample promotions using probability matrices
   - Calculate promotion-based compensation increases

4. **Compensation Events**: Model salary adjustments
   - Apply COLA to all active employees
   - Apply merit increases to eligible employees
   - Generate raise events with effective dates

5. **DC Plan Events**: Model retirement plan activity
   - Determine eligibility for new hires and continuing employees
   - Generate enrollment events (auto-enrollment and voluntary)
   - Calculate employee and employer contributions
   - Track vesting schedule progression
   - Process forfeitures from terminated unvested participants
   - Determine HCE status for compliance tracking

#### Phase 4: State Accumulation
1. **Temporal State Tracking**: Maintain year-over-year state
   - Enrollment state accumulator (participation history)
   - Deferral rate state accumulator (contribution elections)
   - Vesting state accumulator (vesting schedule progression)

2. **Snapshot Generation**: Create point-in-time workforce views
   - Aggregate all events up to current year
   - Calculate current compensation, headcount, demographics
   - Determine active/terminated status for each employee

#### Phase 5: Validation
1. **Data Quality Tests**: Automated validation checks
   - No duplicate employee IDs within year
   - No terminations before hire dates
   - Compensation values within expected bounds
   - Contribution rates within regulatory limits (0-100%)
   - Enrollment dates align with eligibility rules

2. **Business Logic Tests**: Verify simulation logic
   - Headcount totals match expected ranges
   - Compensation totals align with budget assumptions
   - Plan participation rates are reasonable
   - Vesting calculations are accurate

#### Phase 6: Reporting
1. **Fact Tables**: Generate final analytical outputs
   - `fct_yearly_events`: Complete event log with metadata
   - `fct_workforce_snapshot`: Year-end workforce state
   - `fct_dc_plan_contributions`: Contribution projections
   - `fct_cost_projections`: Multi-year cost forecasts

2. **Excel Exports**: Generate stakeholder reports
   - Workforce snapshots by year and scenario
   - Financial metrics (total compensation, headcount, contributions)
   - Event logs (audit trail)
   - Metadata sheets (git SHA, random seed, configuration)

### 4.3 Multi-Year Execution

For simulations spanning multiple years (e.g., 2025-2027):
- Year 1 reads baseline workforce from input data
- Year 2 reads Year 1 workforce snapshot + Year 1 state accumulators
- Year 3 reads Year 2 workforce snapshot + Year 2 state accumulators
- Events compound year-over-year (hires become eligible for promotion, etc.)

### 4.4 Batch Scenario Processing

For multi-scenario analysis:
- Each scenario runs in complete isolation with dedicated database
- Scenarios share input data but differ in assumptions (e.g., high/low growth)
- Outputs are stored in timestamped directories for version control
- Comparison reports highlight differences across scenarios

---

## 5. Outputs

### 5.1 Primary Analytical Outputs

| Output Table | Description | Key Metrics | Grain |
|:-------------|:------------|:------------|:------|
| `fct_workforce_snapshot` | Year-end workforce state | Headcount, total compensation, demographics | Scenario × Year × Employee |
| `fct_yearly_events` | Complete event log | Event counts by type, event metadata | Scenario × Year × Event |
| `fct_dc_plan_contributions` | Retirement plan contributions | Employee deferrals, employer match, total contributions | Scenario × Year × Employee |
| `fct_cost_projections` | Multi-year cost forecasts | Total compensation cost, benefit costs, headcount costs | Scenario × Year |
| `fct_enrollment_metrics` | Plan participation analytics | Enrollment rate, average deferral rate, participation trends | Scenario × Year × Plan |
| `fct_vesting_metrics` | Vesting progression tracking | Vested balance, forfeiture amounts, vesting percentage | Scenario × Year × Employee |

### 5.2 Excel Exports (Batch Processing)

Each batch run creates a timestamped directory with Excel workbooks:

**File Structure**: `outputs/batch_YYYYMMDD_HHMMSS/scenario_name/scenario_name_export.xlsx`

**Excel Workbook Sheets**:
1. **Workforce_Snapshot**: Year-end headcount and compensation
2. **Financial_Metrics**: Total cost projections by year
3. **Event_Summary**: Event counts by type and year
4. **DC_Plan_Contributions**: Retirement plan contribution projections
5. **Enrollment_Metrics**: Plan participation and deferral rates
6. **Metadata**: Git commit SHA, random seed, simulation timestamp, configuration parameters

### 5.3 Audit Trail Outputs

| Output | Purpose | Contents |
|:-------|:--------|:---------|
| Database file (`*.duckdb`) | Complete simulation database | All input data, intermediate tables, final outputs, event log |
| Git commit SHA | Code version tracking | Exact code version used for simulation |
| Random seed | Reproducibility | Seed value for deterministic random sampling |
| Configuration snapshot | Parameter documentation | Complete simulation configuration as JSON |
| Execution logs | Troubleshooting and audit | Timestamps, stage execution times, validation results |

### 5.4 Data Quality Reports

Automated during pipeline execution:
- **Test Results**: Pass/fail status for all data quality tests (90+ tests)
- **Validation Warnings**: Non-fatal data quality issues flagged for review
- **Coverage Metrics**: % of employees with events, % of eligible employees enrolled, etc.

---

## 6. Data Flows

### 6.1 Input → Processing → Output Flow

```
CSV Files (data/)
    ↓
Staging Tables (stg_*)
    ↓
Intermediate Models (int_*)
    ├→ Event Generation (int_*_events)
    ├→ State Accumulators (int_*_accumulator)
    └→ Business Logic (int_*)
    ↓
Fact Tables (fct_*)
    ├→ fct_workforce_snapshot
    ├→ fct_yearly_events
    ├→ fct_dc_plan_contributions
    └→ fct_cost_projections
    ↓
Excel Exports (.xlsx)
```

### 6.2 Data Retention

- **Input Data**: Retained in CSV format, versioned with Git
- **Simulation Databases**: Retained permanently for audit purposes
- **Excel Exports**: Retained permanently for stakeholder distribution
- **Logs**: Retained for 90 days (configurable)

---

## 7. Technology Stack

| Component | Technology | Version | Purpose |
|:----------|:-----------|:--------|:--------|
| System Version | Fidelity PlanAlign Engine | 1.0.0 | Overall system version (Semantic Versioning) |
| Database | DuckDB | 1.0.0 | Analytical database and event store |
| Transformation | dbt-core | 1.8.8 | SQL-based data modeling |
| Orchestration | Python (planalign_orchestrator) | 3.11 | Workflow execution and coordination |
| CLI | Rich + Typer | 1.0.0 | Command-line interface |
| Validation | Pydantic | 2.7.4 | Data validation and type safety |
| Reporting | openpyxl / pandas | Latest | Excel export generation |

**Version Tracking**: Every simulation output includes the system version in metadata for audit trail compliance.

---

## 8. Security and Compliance

### 8.1 Data Security

- **Local Storage**: All data stored on-premises, no cloud transmission
- **Access Control**: File system permissions control access to databases and exports
- **Encryption**: Data at rest encryption via file system (if configured by IT)
- **Audit Trail**: Complete event log with UUID-stamped immutable records

### 8.2 Data Privacy

- **PII Handling**: Employee IDs are anonymized identifiers (not SSN or other sensitive PII)
- **Compensation Data**: Treated as confidential financial information
- **Access Logging**: Database access can be logged via DuckDB audit extensions (if enabled)

### 8.3 Reproducibility and Auditability

- **Deterministic Results**: Same inputs + same seed = same outputs (bit-for-bit)
- **Version Control**: All code, configuration, and input data tracked in Git
- **Metadata Recording**: Every simulation records git SHA, seed, timestamp, configuration
- **Event Sourcing**: Complete workforce history reconstructable from event log

---

## 9. Limitations and Disclaimers

### 9.1 Model Limitations

1. **Projection Uncertainty**: All simulations are projections based on assumptions; actual results will differ
2. **Simplified Modeling**: Annual event frequency (not monthly/daily granularity)
3. **Independent Events**: Some workforce events may be correlated in reality (not modeled)
4. **Regulatory Compliance**: Model does not enforce IRS compliance testing (informational only)

### 9.2 Data Quality Dependencies

1. **Input Accuracy**: Outputs are only as accurate as input data quality
2. **Assumption Validity**: Projections depend on validity of turnover, hiring, and compensation assumptions
3. **Historical Patterns**: Model assumes historical patterns predict future behavior

### 9.3 Use Case Scope

**Intended Use**:
- Strategic workforce planning (3-5 year horizons)
- Retirement plan cost projections and scenario analysis
- Budget forecasting and sensitivity analysis
- Policy impact modeling (e.g., changes to match formula)

**NOT Intended For**:
- Individual employee benefit calculations (use official benefits administration system)
- Regulatory compliance filings (use certified actuarial systems)
- Real-time operational reporting (use HRIS/payroll systems)
- Legal or contractual obligations (consult official systems of record)

---

## 10. Contact Information

**Technical Owner**: [To Be Completed]
**Business Owner**: [To Be Completed]
**Data Governance Contact**: [To Be Completed]
**Legal Review Contact**: [To Be Completed]

---

## 11. Document Control

| Version | Date | Author | Changes |
|:--------|:-----|:-------|:--------|
| 1.0 | 2025-11-20 | System Documentation | Initial legal review documentation |

---

## Appendix A: Sample Data Dictionary

### A.1 Employee Event Schema

| Field | Type | Description | Example |
|:------|:-----|:------------|:--------|
| event_id | UUID | Unique event identifier | `550e8400-e29b-41d4-a716-446655440000` |
| employee_id | VARCHAR | Employee identifier | `EMP_2025_001` |
| scenario_id | VARCHAR | Scenario identifier | `baseline_2025` |
| plan_design_id | VARCHAR | DC plan identifier | `standard_401k` |
| event_type | VARCHAR | Event type code | `HIRE`, `TERMINATION`, `DC_PLAN_CONTRIBUTION` |
| effective_date | DATE | Event effective date | `2025-01-15` |
| simulation_year | INTEGER | Simulation year | `2025` |
| event_payload | JSON | Event-specific data | `{"annual_compensation": 125000.00, "department": "Engineering"}` |

### A.2 DC Plan Contribution Schema

| Field | Type | Description | Example |
|:------|:-----|:------------|:--------|
| employee_id | VARCHAR | Employee identifier | `EMP_2025_001` |
| scenario_id | VARCHAR | Scenario identifier | `baseline_2025` |
| plan_design_id | VARCHAR | DC plan identifier | `standard_401k` |
| simulation_year | INTEGER | Contribution year | `2025` |
| deferral_rate | DECIMAL(5,4) | Employee deferral % | `0.0600` (6%) |
| employee_contribution | DECIMAL(15,2) | Employee contribution amount | `7500.00` |
| employer_match | DECIMAL(15,2) | Employer match amount | `7500.00` |
| vesting_percentage | DECIMAL(5,4) | Vested % of employer match | `0.3333` (33.33%) |

---

**END OF DOCUMENT**
