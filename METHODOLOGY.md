# Fidelity PlanAlign Engine — Methodology Documentation

**Prepared for**: Legal and Compliance Review (FINRA e-Review Submission)
**System Version**: 1.0.0 ("Foundation")
**Document Date**: March 2026
**Classification**: Methodology Reference — Confidential

---

## Document Version History

| Version | Date       | Author        | Summary of Changes                                         |
| ------- | ---------- | ------------- | ---------------------------------------------------------- |
| 1.0     | March 2026 | [Author Name] | Initial methodology document for FINRA e-review submission |

---

## Table of Contents

1. Executive Summary
2. Purpose and General Use
3. Inputs
4. Assumptions
5. What Can Be Modeled
6. Outputs
7. Definitions and Key Terms
8. Regulatory and Compliance Framework
9. Audit and Reproducibility Controls
10. Limitations and Exclusions

---

## 1. Executive Summary

Fidelity PlanAlign Engine is a workforce simulation platform that produces estimated multi-year projections of employee population dynamics, compensation trajectories, and defined contribution (DC) retirement plan costs. The system uses an event-sourced architecture to maintain a log of every modeled workforce and plan administration event, intended to support auditability and review.

The platform is designed for plan sponsors and their advisors to estimate the potential financial impact of retirement plan design changes — such as match formula modifications, auto-enrollment strategies, and vesting schedule alternatives — against projected workforce demographics. Outputs are intended to be deterministic and reproducible given the same configuration and random seed, supporting transparent review.

PlanAlign Engine does **not** provide investment advice, individual participant recommendations, or fiduciary guidance. It is a hypothetical projection and cost-estimation tool intended to inform plan design decisions. **All outputs are estimates and projections based on user-supplied inputs and configurable assumptions. Actual results will vary, potentially materially, from projections.** The tool does not determine, certify, or guarantee compliance with any federal, state, or local law or regulation, including but not limited to the Internal Revenue Code or ERISA.

---

## 2. Purpose and General Use

### 2.1 Intended Use

PlanAlign Engine is used to:

- **Estimate workforce demographics** over a multi-year horizon (typically 5–10 years), including projected headcount, age and tenure distributions, and compensation levels.
- **Estimate defined contribution plan costs** under current and proposed plan designs, including projected employer matching contributions, nonelective (core) contributions, and vesting-related forfeitures.
- **Compare plan design scenarios** side-by-side (e.g., current match formula vs. proposed Safe Harbor formula) to estimate the cost differential and identify potentially affected employee populations.
- **Support plan amendment analysis** by estimating the projected impact of changes to auto-enrollment defaults, deferral escalation schedules, eligibility requirements, and match formulas.
- **Document projection assumptions, inputs, and event-level detail** to facilitate regulatory and fiduciary review.

### 2.2 Intended Users

- Plan sponsors evaluating retirement plan design changes
- Retirement plan consultants and advisors
- Actuarial and benefits teams performing cost projections
- Compliance officers reviewing plan amendment impacts

### 2.3 What PlanAlign Engine Is Not

- It is **not** an investment advisory tool and does not model investment returns or asset allocation.
- It is **not** a recordkeeping system and does not process actual participant transactions.
- It is **not** a nondiscrimination testing engine, although it produces HCE classifications and demographic data that can support such testing.
- It does **not** model non-qualified deferred compensation plans (IRC Section 409A).

---

## 3. Inputs

### 3.1 Census Data

The primary input is an employee census file containing the current workforce population. Required fields include:

| Field                 | Description                          | Example         |
| --------------------- | ------------------------------------ | --------------- |
| Employee ID           | Unique identifier                    | EMP_2025_000001 |
| Hire Date             | Original date of hire                | 2018-03-15      |
| Date of Birth         | For age calculations                 | 1985-07-22      |
| Annual Compensation   | Current base salary                  | $125,000.00     |
| Job Level             | Position tier (1–5)                  | 3               |
| Department            | Organizational unit                  | Engineering     |
| Employment Status     | Active or terminated                 | Active          |
| Current Deferral Rate | Existing plan election (if enrolled) | 6%              |

Census deferral rates, when available, are used as the starting contribution election for currently enrolled participants. The system normalizes percentage formats automatically (e.g., 7.5 is converted to 0.075).

### 3.2 Simulation Parameters

Core parameters that define the projection scope:

| Parameter                 | Default   | Description                            |
| ------------------------- | --------- | -------------------------------------- |
| Simulation Period         | 2025–2029 | Start and end years for projection     |
| Random Seed               | 42        | Deterministic seed for reproducibility |
| Target Growth Rate        | 3.0%      | Annual net headcount growth target     |
| Total Termination Rate    | 12.0%     | Annual base turnover for all employees |
| New Hire Termination Rate | 25.0%     | First-year turnover (elevated)         |

### 3.3 Compensation Configuration

| Parameter          | Default              | Description                                             |
| ------------------ | -------------------- | ------------------------------------------------------- |
| COLA Rate          | 2.5% per year        | Cost-of-living adjustment (per config_cola_by_year.csv) |
| Merit Budget       | 2.0%                 | Annual merit increase pool                              |
| Growth Target      | 0.5%                 | Target average compensation growth                      |
| Growth Tolerance   | +/- 0.5%             | Acceptable variance from growth target                  |
| Calculation Method | Full Year Equivalent | Annualization method for partial-year employees         |

**Promotion Compensation**: Increases of 15–25% of the midpoint of the new compensation band (uniformly distributed), subject to a safety cap of 30% or $500,000 per event. Level-specific overrides are configurable.

**New Hire Compensation**: Based on a percentile of the compensation band for the assigned job level. Default percentiles range from the 30th percentile (entry-level) to the 70th percentile (executive), with a 5% standard deviation for variance.

**Raise Timing Distribution**: Merit raises are distributed across calendar months according to a configurable monthly profile. The default "general corporate" profile concentrates raises in January (28%), July (23%), and April (18%), reflecting common fiscal and budget cycles.

### 3.4 Defined Contribution Plan Design Inputs

#### Eligibility

| Parameter      | Default                 | Description                            |
| -------------- | ----------------------- | -------------------------------------- |
| Waiting Period | 0 days                  | Service requirement before eligibility |
| Minimum Age    | 21 years                | IRC Section 401(k) age requirement     |
| Plan Year      | January 1 – December 31 | Annual plan cycle                      |

#### Auto-Enrollment

| Parameter             | Default         | Description                                     |
| --------------------- | --------------- | ----------------------------------------------- |
| Enabled               | Yes             | Master auto-enrollment toggle                   |
| Window                | 45 days         | Days after eligibility before auto-enrollment   |
| Default Deferral Rate | 2.0%            | Initial contribution rate                       |
| Opt-Out Grace Period  | 30 days         | No-penalty withdrawal window                    |
| Scope                 | New hires only  | Applies to employees hired on/after cutoff date |
| Hire Date Cutoff      | January 1, 2020 | Grandfathering boundary for auto-enrollment     |

**Opt-Out Rates** are configurable by age group and income level:

- Age-based base rates range from 3% (age 56+) to 10% (age 18–30).
- Income-based multipliers adjust the base rate: low income 1.20x, moderate 1.00x, high 0.70x, executive 0.50x.

#### Employer Match Formulas

The system supports five match formula types:

| Formula           | Structure                        | Maximum Match        |
| ----------------- | -------------------------------- | -------------------- |
| Simple Match      | 50% on all deferrals up to 6%    | 3.0% of compensation |
| Tiered Match      | 100% on first 3%, 50% on next 2% | 4.0% of compensation |
| Stretch Match     | 25% on first 12%                 | 3.0% of compensation |
| Safe Harbor Basic | 100% on first 3%, 50% on 3–5%    | 4.0% of compensation |
| QACA Safe Harbor  | 100% on first 1%, 50% on 1–6%    | 3.5% of compensation |

Match tier rates, boundaries, and caps are fully configurable per plan design.

#### Match Eligibility Requirements

| Parameter                        | Default | Description                              |
| -------------------------------- | ------- | ---------------------------------------- |
| Apply Eligibility                | Yes     | Enforce eligibility rules for match      |
| Require Active at Year-End       | Yes     | Must be employed on December 31          |
| Minimum Annual Hours             | 1,000   | Hours-of-service threshold               |
| Allow New Hires                  | Yes     | Active new hires can qualify             |
| Exclude New Hire Terminations    | Yes     | Year-of-hire terminations are ineligible |
| Exclude Experienced Terminations | Yes     | All terminated employees are ineligible  |

#### Employer Core (Nonelective) Contribution

| Option            | Description                                                    |
| ----------------- | -------------------------------------------------------------- |
| None              | No core contribution                                           |
| Flat              | Fixed percentage (default: 1% of compensation)                 |
| Graded by Service | Increases with tenure: 1% (0–2 yrs), 2% (3–5 yrs), 3% (6+ yrs) |

#### Deferral Rate Escalation

| Parameter              | Default   | Description                        |
| ---------------------- | --------- | ---------------------------------- |
| Enabled                | Yes       | Annual automatic deferral increase |
| Annual Increment       | 1.0%      | Amount added each year             |
| Maximum Rate Cap       | 10.0%     | Ceiling for auto-escalation        |
| Effective Date         | January 1 | Annual escalation date             |
| First Escalation Delay | 1 year    | Waiting period after enrollment    |

#### Vesting Schedules

| Schedule Type | Structure                   | Application                  |
| ------------- | --------------------------- | ---------------------------- |
| Immediate     | 100% vested from day one    | Safe Harbor matches          |
| 2-Year Cliff  | 0% until 2 years, then 100% | QACA Safe Harbor             |
| 3-Year Cliff  | 0% until 3 years, then 100% | Standard match               |
| 6-Year Graded | 20% per year of service     | Standard match (alternative) |

### 3.5 IRS Regulatory Limits

IRS contribution and compensation limits are maintained in a seed file (config_irs_limits.csv) indexed by plan year:

| Limit (2025 values)                   | Amount   | IRC Section         |
| ------------------------------------- | -------- | ------------------- |
| Elective Deferral Limit               | $23,500  | 402(g)              |
| Catch-Up Contribution Limit (age 50+) | $31,000  | 414(v)              |
| Super Catch-Up (ages 60–63)           | $34,750  | 414(v) (SECURE 2.0) |
| Compensation Limit                    | $350,000 | 401(a)(17)          |
| Annual Additions Limit                | $70,000  | 415(c)              |
| HCE Compensation Threshold            | $160,000 | 414(q)              |

These limits are projected forward by year and applied programmatically as caps during contribution calculations. Users are responsible for verifying that seed file values reflect current and projected IRS guidance.

### 3.6 Demographic Configuration Seeds

The following seed files define demographic segmentation and hazard probabilities:

| Seed File                                        | Purpose                                                     |
| ------------------------------------------------ | ----------------------------------------------------------- |
| config_age_bands.csv                             | Age band boundaries (< 25, 25–34, 35–44, 45–54, 55–64, 65+) |
| config_tenure_bands.csv                          | Tenure band boundaries (< 2, 2–4, 5–9, 10–19, 20+)          |
| config_job_levels.csv                            | Job level definitions with compensation bands               |
| config_new_hire_age_distribution.csv             | Probabilistic age distribution for new hires                |
| config_termination_hazard_age_multipliers.csv    | Termination probability adjustments by age                  |
| config_termination_hazard_tenure_multipliers.csv | Termination probability adjustments by tenure               |
| config_promotion_hazard_age_multipliers.csv      | Promotion probability adjustments by age                    |
| config_promotion_hazard_tenure_multipliers.csv   | Promotion probability adjustments by tenure                 |
| config_cola_by_year.csv                          | Cost-of-living adjustment rates by calendar year            |
| config_irs_limits.csv                            | IRS limits by plan year (2025–2035)                         |
| config_raise_timing_distribution.csv             | Monthly distribution of merit raise effective dates         |
| config_default_deferral_rates.csv                | Default deferral rates by age and income segment            |

---

## 4. Assumptions

### 4.1 Stochastic Modeling

| Assumption                        | Description                                                                                                                             |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **Deterministic Reproducibility** | All stochastic processes use a configurable random seed (default: 42). Identical inputs and seed produce identical outputs across runs. |
| **Uniform Random Distribution**   | Random numbers are drawn from a uniform [0, 1) distribution for hazard-based event determination.                                       |
| **Multiplicative Hazard Model**   | Event probabilities are calculated as: Base Rate x Age Multiplier x Tenure Multiplier.                                                  |
| **Event Independence**            | Workforce events (termination, promotion, merit) are treated as independent processes. The model does not implement competing risks.    |
| **Proportional Hazards**          | Multipliers are constant within a given age/tenure band for a simulation year and are applied proportionally to the base hazard rate.   |

### 4.2 Hiring and Growth

| Assumption                    | Description                                                                                                                                                    |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target-Based Hiring**       | The number of new hires is calculated algebraically to achieve the target growth rate after accounting for projected terminations (E077 deterministic solver). |
| **New Hire Age Distribution** | New hire ages are sampled from a discrete probability distribution centered around ages 28–32, reflecting a mid-career-weighted labor market.                  |
| **New Hire Compensation**     | Starting salary is set at a configurable percentile of the compensation band for the assigned job level, with a 5% standard deviation for variance.            |
| **First-Year Turnover**       | New hires experience an elevated termination hazard (25% vs. 12% overall), reflecting industry patterns of higher first-year attrition.                        |

### 4.3 Compensation

| Assumption              | Description                                                                                                                            |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **COLA Application**    | A cost-of-living adjustment (default 2.5%) is applied annually per config_cola_by_year.csv.                                            |
| **Merit Increases**     | Merit raises are budget-constrained (default 2.0% of payroll) and distributed to eligible employees based on tenure and level factors. |
| **Promotion Increases** | Promotions carry a compensation increase of 15–25% of the new level's midpoint, uniformly distributed.                                 |
| **Annualization**       | Partial-year employees are annualized using the Full Year Equivalent method for compensation growth calculations.                      |
| **Raise Timing**        | Merit raises are distributed across calendar months according to a configurable profile, not applied uniformly on January 1.           |

### 4.4 Plan Enrollment

| Assumption                     | Description                                                                                                                                                                                                     |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Auto-Enrollment Assumption** | The model assumes the plan sponsor has adopted auto-enrollment. The auto-enrollment parameters are configurable and are not intended to represent or certify compliance with any specific SECURE Act provision. |
| **Opt-Out Behavior**           | Opt-out rates vary by age (3–10%) and income level (0.50x–1.20x multiplier), based on industry participation data.                                                                                              |
| **Proactive Enrollment**       | A portion of eligible employees (25–75%, varying by age) will voluntarily enroll before the auto-enrollment deadline.                                                                                           |
| **Year-over-Year Conversion**  | Non-participants have a 3–8% annual probability of voluntarily enrolling in subsequent years, varying by age, income, and tenure.                                                                               |
| **Census Deferral Rates**      | When census data includes existing deferral rates, those rates are used as starting elections. A fallback rate of 3% is applied for pre-enrolled employees without census data.                                 |

### 4.5 Employer Contributions

| Assumption                     | Description                                                                                                                                                                                                                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Year-End Match Eligibility** | The default configuration requires employees to be active on December 31 to receive the employer match. Year-of-hire terminations are excluded.                                                                                                                                                              |
| **Hours-of-Service Threshold** | Employees must work at least 1,000 hours annually to qualify for employer matching contributions. **The model assumes all active full-time employees meet this threshold; individual hours are not tracked.** See Section 10 (Limitations) for further detail on this simplification.                        |
| **Match Formula Application**  | The employer match is calculated annually based on the employee's deferral rate and eligible compensation, subject to formula-specific caps.                                                                                                                                                                 |
| **IRS Limit Application**      | Employee deferrals and total annual additions are capped at the IRS limits configured in the seed file for the applicable plan year. Catch-up contributions are modeled for employees age 50 and older. These caps reflect user-configured values and do not constitute a determination of legal compliance. |
| **Vesting Accrual**            | Vesting is tracked by contribution source (match, nonelective, profit-sharing) and accrues based on the applicable schedule (immediate, cliff, or graded).                                                                                                                                                   |

### 4.6 Termination and Forfeiture

| Assumption                    | Description                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Termination Hazard**        | The base hazard rate for new hires is 42%, which represents the starting probability before age and tenure multipliers are applied. After multipliers, the model targets an effective first-year turnover rate of approximately 25% for new hires and 12% overall annual turnover. The distinction between base hazard (42%) and effective rate (25%) reflects the multiplicative application of demographic adjustment factors (see Section 3.2). |
| **Forfeiture on Termination** | Unvested employer contributions are forfeited upon termination. Forfeiture amounts are calculated based on the vesting percentage at termination date.                                                                                                                                                                                                                                                                                             |
| **No Rehire Modeling**        | The current model does not simulate employee rehire events. Terminated employees are not re-entered into the workforce.                                                                                                                                                                                                                                                                                                                            |

### 4.7 Temporal

| Assumption                           | Description                                                                                              |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| **Calendar Plan Year**               | The plan year runs January 1 through December 31.                                                        |
| **Annual Processing**                | Simulations process one year at a time, sequentially, with state carried forward via accumulator models. |
| **Point-in-Time Snapshots**          | Workforce snapshots reflect status as of December 31 of each simulation year.                            |
| **No Intra-Year Investment Returns** | The model does not project account balances or investment performance within or across plan years.       |

---

## 5. What Can Be Modeled

### 5.1 Workforce Lifecycle Events

| Event Type      | Description                                                                                                                                                  |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Hire**        | New employee onboarding with age, level, compensation, and department assignment. Hiring volume is calibrated to achieve a target net headcount growth rate. |
| **Termination** | Employment separation with reason code (voluntary, involuntary, retirement, death, disability). Probability is hazard-based with age and tenure multipliers. |
| **Promotion**   | Advancement to a higher job level with associated compensation increase. Probability is hazard-based with level-dampening to limit senior-level frequency.   |
| **Merit Raise** | Annual compensation adjustment reflecting COLA, merit, and tenure-based components. Timing is distributed across the calendar year.                          |

### 5.2 Defined Contribution Plan Events

| Event Type                     | Description                                                                                                                         |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Plan Eligibility**           | Determination of when an employee satisfies age, service, and hours requirements to participate.                                    |
| **Enrollment**                 | Deferral election event — either auto-enrollment at the default rate, proactive voluntary enrollment, or year-over-year conversion. |
| **Deferral Rate Change**       | Modifications to contribution rate via auto-escalation, match-responsive adjustments, or voluntary election changes.                |
| **Employee Contribution**      | Pre-tax, Roth, after-tax, and catch-up contributions calculated per pay period, subject to IRS limits.                              |
| **Employer Match**             | Formula-based matching contribution calculated annually, subject to eligibility requirements and formula caps.                      |
| **Employer Core Contribution** | Nonelective contribution (flat or graded by service) allocated to eligible employees regardless of deferral election.               |
| **Vesting**                    | Service-based accrual of ownership rights over employer contributions, tracked by source.                                           |
| **Forfeiture**                 | Recapture of unvested employer contributions upon employee termination.                                                             |
| **HCE Determination**          | Annual classification of Highly Compensated Employees based on prior-year compensation and the IRS threshold.                       |

### 5.3 Scenario Comparison

The system supports simultaneous modeling of multiple plan design scenarios with full data isolation. Typical comparisons include:

- **Current vs. proposed match formula** (e.g., Simple Match vs. Safe Harbor)
- **Auto-enrollment impact** (enabled vs. disabled; varying default rates)
- **Deferral escalation alternatives** (1% annual vs. 2% annual; varying caps)
- **Eligibility changes** (immediate vs. 1-year waiting period)
- **Growth scenarios** (baseline 3% vs. high-growth 10% vs. hiring freeze)
- **Core contribution alternatives** (no core vs. flat 1% vs. graded by service)
- **Winners and losers analysis** (which employee segments are financially impacted by a plan change, segmented by age and tenure bands)

### 5.4 Analytics and Reporting

| Analysis                           | Description                                                                                                                                                                                        |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Employer Cost Projection**       | Total employer match and core contribution cost by year, with breakdowns by formula component.                                                                                                     |
| **Participation Rate Forecasting** | Projected enrollment and deferral rates over time, accounting for auto-enrollment, escalation, and opt-out behavior.                                                                               |
| **Compensation Growth Analysis**   | Year-over-year average compensation change using three methodologies: current workforce (all employees), continuous employees only, and incumbent (present in both years).                         |
| **Demographic Shift Analysis**     | Projected changes in workforce age and tenure distributions driven by hiring, termination, and promotion patterns.                                                                                 |
| **Winners and Losers**             | Identification of employee segments that receive more or less employer contributions under a proposed plan change compared to the current plan, segmented by age band, tenure band, and job level. |

---

## 6. Outputs

### 6.1 Event Audit Trail (fct_yearly_events)

The primary output is an event log containing the modeled workforce and plan administration events generated during the simulation. Each record includes:

- **Event ID**: Universally unique identifier (UUID)
- **Employee ID**: Identifier linking to census record
- **Event Type**: Classification (hire, termination, promotion, merit, enrollment, contribution, vesting, forfeiture, HCE status)
- **Effective Date**: Date the event takes effect
- **Simulation Year**: Projection year
- **Event Details**: Structured payload specific to event type
- **Scenario ID / Plan Design ID**: Isolation keys for scenario comparison
- **Timestamp**: Record creation time

Within a completed simulation run, individual event records are not modified. See Section 9.2 for details on the event persistence strategy.

### 6.2 Workforce Snapshot (fct_workforce_snapshot)

An annual point-in-time view of every employee as of December 31 of each simulation year. Key fields include:

- **Employment Status**: Active, terminated, or detailed status code (continuous active, new hire active, new hire terminated, continuous terminated)
- **Compensation**: Current annual compensation, prorated compensation (for partial-year employees), and gross compensation
- **Demographics**: Current age, current tenure, age band, tenure band, job level
- **Enrollment State**: Enrollment date, current deferral rate, auto-enrollment status
- **Vesting State**: Vested balances by source (match, nonelective), total vested employer contribution

### 6.3 Employer Match Detail (fct_employer_match_events)

Annual employer match calculations for each eligible employee, including:

- Match formula applied (name and type)
- Employee deferral rate and eligible compensation
- Annual employee deferrals
- Calculated employer match amount (before and after caps)
- Effective match rate as a percentage of compensation
- Match cap applied indicator

### 6.4 Compensation Growth Summary (fct_compensation_growth)

Year-over-year compensation analysis using three standard methodologies:

| Methodology        | Population                                                       | Use Case                        |
| ------------------ | ---------------------------------------------------------------- | ------------------------------- |
| **A — Current**    | All employees with prorated compensation                         | Total payroll projection        |
| **B — Continuous** | Employees active full year (excludes new hires and terminations) | Underlying compensation trend   |
| **C — Incumbent**  | Employees active in both the current and prior year              | Same-person compensation growth |

### 6.5 Batch Export

For multi-scenario analysis, the system produces Excel workbooks containing:

- Workforce snapshots by year
- Event summaries by type
- Employer cost projections
- Scenario comparison metrics
- Metadata sheet with configuration parameters, software version, and git commit SHA for traceability

---

## 7. Definitions and Key Terms

### Workforce Terms

**Active Employee**: An individual currently employed by the plan sponsor as of the measurement date (December 31 of the simulation year).

**Age Band**: A categorical grouping of employees by age. The system uses six standard bands: under 25, 25–34, 35–44, 45–54, 55–64, and 65 and over. Bands use a lower-bound-inclusive, upper-bound-exclusive convention (e.g., an employee aged 35 is in the 35–44 band).

**Census**: The input file containing the current employee population with demographic, compensation, and plan election data.

**Continuous Active**: An employee who was active on both January 1 and December 31 of a simulation year.

**COLA (Cost-of-Living Adjustment)**: An annual across-the-board compensation increase intended to offset inflation, applied at a configured rate (default 2.5%).

**Full Year Equivalent (FYE)**: An annualization method that prorates compensation for employees hired or terminated mid-year to reflect what they would have earned over a full calendar year.

**Hazard Rate**: The probability that an event (termination, promotion) occurs for a given employee in a given year. Calculated as a base rate multiplied by age and tenure adjustment factors.

**Job Level**: A position tier in the organizational hierarchy (1 = Staff, 2 = Manager, 3 = Senior Manager, 4 = Director, 5 = Vice President), each with defined compensation bands.

**Merit Increase**: A performance- or tenure-based compensation adjustment, distinct from COLA and promotion increases.

**New Hire Termination**: A termination occurring within the employee's first year of hire. These employees are typically excluded from year-end employer match eligibility.

**Tenure Band**: A categorical grouping of employees by years of service. The system uses five standard bands: under 2 years, 2–4, 5–9, 10–19, and 20 or more.

### Defined Contribution Plan Terms

**Annual Additions**: The sum of all contributions (employee deferrals, employer match, employer nonelective) allocated to a participant's account in a plan year. Subject to the IRC Section 415(c) limit ($70,000 in 2025).

**Auto-Enrollment**: A plan feature, as modeled in this tool, that automatically enrolls eligible employees at a default deferral rate unless they affirmatively opt out. The model's auto-enrollment parameters are configurable and should be set to reflect the terms of the applicable plan document.

**Auto-Escalation**: An annual automatic increase in an enrolled participant's deferral rate (typically 1% per year) up to a maximum cap (typically 10%).

**Catch-Up Contribution**: An additional elective deferral available to participants who are age 50 or older by the end of the plan year, up to the IRC Section 414(v) limit ($31,000 in 2025).

**Core Contribution (Nonelective)**: An employer contribution allocated to eligible employees regardless of whether they make elective deferrals. May be a flat percentage or graded by years of service.

**Deferral Rate**: The percentage of compensation that a participant elects to contribute to the plan as pre-tax or Roth deferrals.

**Elective Deferral**: A voluntary contribution made by a participant from their compensation on a pre-tax or Roth basis, subject to the IRC Section 402(g) annual limit ($23,500 in 2025).

**Employer Match**: A contribution made by the employer based on the participant's elective deferrals, calculated according to the plan's match formula and subject to eligibility requirements.

**Forfeiture**: The portion of an employer contribution that is not vested at the time of a participant's termination. Forfeited amounts revert to the plan and may be reallocated to remaining participants or used to offset future employer contributions.

**Highly Compensated Employee (HCE)**: An employee whose compensation exceeds the IRS threshold ($160,000 in 2025) or who is in the top 20% of earners, as defined by IRC Section 414(q). HCE status is relevant to nondiscrimination testing.

**Match Eligibility**: The set of requirements an employee must satisfy to receive the employer match, which may include year-end active employment, minimum hours of service, and completion of a waiting period.

**Plan Year**: The 12-month period used for plan administration and IRS compliance. The system assumes a calendar plan year (January 1 through December 31).

**QACA (Qualified Automatic Contribution Arrangement)**: As used in this document, a plan design option that models the match formula and vesting schedule generally associated with IRC Section 401(k)(13) qualified automatic contribution arrangements. Selection of this option in the tool does not constitute a determination that any particular plan qualifies as a QACA.

**Safe Harbor Plan**: As used in this document, a plan design option that models the match formula and immediate vesting requirements generally associated with IRC Section 401(k)(12) safe harbor plans. Selection of this option in the tool does not constitute a determination that any particular plan satisfies safe harbor requirements or is exempt from nondiscrimination testing. Users should consult qualified counsel for safe harbor compliance determinations.

**Super Catch-Up Contribution**: An enhanced catch-up contribution available under SECURE 2.0 for participants aged 60–63, allowing deferrals up to $34,750 in 2025.

**Vesting**: The process by which a participant earns a nonforfeitable right to employer contributions over time. Vesting schedules may be immediate (Safe Harbor), cliff (e.g., 100% after 3 years), or graded (e.g., 20% per year over 6 years).

### Technical Terms

**Event Sourcing**: An architectural pattern in which every change to the system state is captured as an immutable event record. The current state is derived by replaying the event history, enabling full auditability and point-in-time reconstruction.

**Random Seed**: A fixed integer value used to initialize the pseudo-random number generator. Using the same seed with the same inputs and software version is designed to produce identical simulation outputs, supporting reproducibility and verification.

**Scenario**: A named configuration representing a specific set of plan design parameters, growth assumptions, and workforce dynamics. Multiple scenarios can be run independently and compared.

**Simulation Year**: A single calendar year within the projection window. The system processes each simulation year sequentially, carrying forward the accumulated state to the next year.

---

## 8. Regulatory Provisions Reflected in the Model

The following section describes the regulatory provisions that the model's calculations are designed to reflect. **Inclusion in this section does not represent a determination or certification that the tool, or any plan design modeled using the tool, satisfies the legal requirements of any statute or regulation.** Users should consult qualified legal and tax counsel to confirm compliance with applicable law.

### 8.1 Internal Revenue Code Provisions Modeled

The system's calculations are designed to reflect provisions of the following IRC sections:

| IRC Section | Provision                                           | Implementation                                                        |
| ----------- | --------------------------------------------------- | --------------------------------------------------------------------- |
| 401(k)      | Qualified cash-or-deferred arrangement              | Employee elective deferrals modeled with configurable plan parameters |
| 401(a)(17)  | Compensation limit for plan purposes                | $350,000 cap (2025) applied in match and contribution calculations    |
| 401(k)(12)  | Safe harbor matching contribution                   | Match formula option with immediate vesting modeled                   |
| 401(k)(13)  | Qualified automatic contribution arrangement (QACA) | QACA match formula option with 2-year cliff vesting modeled           |
| 401(m)      | Matching and employee contribution rules            | Formula-based matching modeled with caps and eligibility parameters   |
| 402(g)      | Elective deferral annual limit                      | $23,500 (2025) applied as cap per participant                         |
| 414(q)      | Highly compensated employee definition              | $160,000 threshold (2025) applied for HCE classification              |
| 414(v)      | Catch-up contributions for age 50+                  | $31,000 (2025) modeled as additional deferral allowance               |
| 415(c)      | Annual additions limit                              | $70,000 (2025) applied as total contribution cap                      |

All dollar limits reflect user-configured values indexed by plan year in the seed file and projected forward through the simulation window. These values are assumptions and may not reflect final IRS guidance for future years.

### 8.2 ERISA Considerations

The following table describes how the tool's outputs may support — but do not independently satisfy — fiduciary and plan administration obligations under ERISA. The tool does not perform fiduciary functions and does not substitute for the judgment of plan fiduciaries or qualified counsel.

| ERISA Provision                  | How PlanAlign Outputs May Support Review                                                                                                                                                                                                  |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Section 404(a) — Prudent process | Projection outputs, documented assumptions, and scenario comparisons may be used as part of a fiduciary's prudent process in evaluating plan design changes. The tool does not itself constitute a prudent process or fiduciary analysis. |
| Participant record modeling      | The event log models participant-level activity with unique identifiers, supporting traceability of projected events. This is a modeling construct and does not replace plan recordkeeping systems.                                       |
| Contribution source tracking     | Projected contributions are categorized by source (pre-tax, Roth, match, nonelective) consistent with typical plan accounting, to support cost estimation by source.                                                                      |
| Vesting documentation            | Projected vesting is tracked by schedule type and vested percentage per modeled event, to support cost estimation of forfeiture and vesting outcomes.                                                                                     |
| Plan rule consistency            | Plan design parameters are applied consistently across the projected population based on user configuration. Users are responsible for confirming that configured parameters accurately reflect their plan document.                      |

### 8.3 SECURE Act and SECURE 2.0 Provisions Reflected

The following table describes SECURE Act and SECURE 2.0 provisions that the model's parameters are designed to reflect. These are modeling features, not compliance determinations. Users should verify that configured parameters align with the applicable statutory and regulatory requirements as interpreted by qualified counsel.

| Provision                       | How Reflected in Model                                                                                                                                                                                                                                                                                           |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auto-enrollment                 | Configurable auto-enrollment with opt-out grace period. Parameters are user-configurable and are not validated against specific SECURE Act requirements.                                                                                                                                                         |
| Auto-escalation                 | Annual deferral rate increase with configurable cap.                                                                                                                                                                                                                                                             |
| Enhanced catch-up (ages 60–63)  | The model applies an enhanced catch-up limit for participants aged 60–63. The default 2025 value of $34,750 reflects the statutory formula (the greater of $10,000 or 150% of the standard catch-up limit, as indexed). Users should verify this value against final IRS guidance for each applicable plan year. |
| Long-term part-time eligibility | The model includes an hours-of-service parameter (default: 1,000 hours). See Section 10 (Limitations) regarding the simplified hours assumption.                                                                                                                                                                 |

---

## 9. Audit and Reproducibility Controls

### 9.1 Deterministic Reproducibility

Every simulation run is fully deterministic given the same:

1. Census input data
2. Configuration parameters (simulation_config.yaml)
3. Seed files (all config\_\*.csv files)
4. Random seed value
5. Software version

Re-running the simulation with identical inputs is designed to produce identical outputs. This property is intended to enable independent verification. Determinism depends on consistent software version, platform, and input data; changes to any of these may affect output comparability.

### 9.2 Immutable Event Trail

Modeled events are written to the fct_yearly_events table using a delete+insert-by-year strategy. Within a completed simulation run, individual event records are not modified in place. Each event carries a UUID, timestamp, and provenance identifiers (scenario ID, plan design ID, simulation year). Note that re-running a simulation for a given year will replace prior event records for that year; the delete+insert strategy is not a permanent append-only log across runs.

### 9.3 Traceability

Batch export workbooks include a metadata sheet recording:

- Software version and build identifier
- Git commit SHA of the codebase
- Random seed used
- Configuration parameter values
- Execution timestamp
- Scenario identifier

### 9.4 Data Validation

The system includes automated data quality checks designed to detect internal inconsistencies in modeled outputs. These checks test for conditions such as:

- Event uniqueness and referential integrity within the modeled data
- Application of configured IRS limit caps
- Enrollment state continuity across simulation years
- Band configuration completeness (no gaps or overlaps in configured bands)
- Contribution aggregation consistency
- Match eligibility rule application per configured parameters

These are internal consistency checks on modeled data. They do not validate the accuracy of user-supplied inputs, the appropriateness of configured assumptions, or compliance with any legal or regulatory requirement.

---

## 10. Limitations and Exclusions

| Limitation                       | Description                                                                                                                                                 |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No Investment Returns**        | The system does not model account balances, investment returns, asset allocation, or fund performance. Outputs reflect contribution amounts only.           |
| **No Rehire Modeling**           | Terminated employees are not re-entered into the workforce in subsequent simulation years.                                                                  |
| **No Competing Risks**           | Workforce events (termination, promotion, merit) are modeled independently. The occurrence of one event does not directly alter the probability of another. |
| **No Intra-Year Cash Flow**      | Contributions are calculated on an annual basis. The system does not model payroll-period-level cash flows or mid-year true-ups in granular detail.         |
| **No Non-Qualified Plans**       | Deferred compensation under IRC Section 409A is out of scope.                                                                                               |
| **No Nondiscrimination Testing** | While the system produces HCE classifications, it does not perform ADP, ACP, or top-heavy testing calculations.                                             |
| **No State/Local Tax Modeling**  | The system does not model income tax withholding or state-specific regulatory requirements.                                                                 |
| **Static IRS Limit Projections** | Future-year IRS limits are based on assumed indexing in the seed file and may differ from actual published limits.                                          |
| **Simplified Hours Assumption**  | The model assumes all active full-time employees meet the 1,000-hour-of-service threshold. Part-time hour tracking is not modeled.                          |

---

## Important Disclaimers

This document describes the methodology of the Fidelity PlanAlign Engine simulation platform for the purpose of regulatory review. It does not constitute investment advice, legal guidance, tax advice, or a recommendation regarding any specific retirement plan design.

**All projection outputs are hypothetical estimates** based on the stated assumptions and user-supplied inputs. **Actual results will vary from projections, potentially materially.** The model's outputs should not be relied upon as predictions of future outcomes.

The tool does not determine, certify, or guarantee compliance with the Internal Revenue Code, ERISA, the SECURE Act, SECURE 2.0, or any other federal, state, or local law or regulation. References to IRC sections, ERISA provisions, and regulatory requirements throughout this document describe the provisions that the model's calculations are designed to reflect — not legal compliance determinations. Users are responsible for consulting qualified legal, tax, and actuarial counsel to confirm that any plan design satisfies applicable legal requirements.

The tool does not perform fiduciary functions, provide fiduciary advice, or substitute for the independent judgment of plan fiduciaries. Any use of the tool's outputs as part of a fiduciary process is the sole responsibility of the plan fiduciary.

IRS limits and thresholds for future plan years are assumptions based on projected indexing and may differ from actual published IRS guidance. Users should update the applicable seed files when final IRS guidance is available.
