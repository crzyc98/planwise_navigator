# Census File Format Guide (LLM Reformatting Reference)

This document is meant to be handed to an LLM together with a raw/arbitrary
census export. The LLM should use it to map the source file's columns onto
the canonical schema below and produce a cleaned CSV or XLSX file ready for
upload to PlanAlign Engine.

Source of truth in the codebase: `planalign_api/services/census_schema.py`
(canonical fields + aliases) and `dbt/models/staging/stg_census_data.sql`
(how columns are cast and defaulted once ingested). If those files and this
doc ever disagree, the code wins — but this doc is kept in sync with them
(`tests/test_census_schema.py` fails if a field is missing here). Analysts see
the same field list in Studio: Import Data → "What should the census include?"
(served by `GET /api/census/schema`).

## Instructions for the LLM doing the reformatting

Given a raw census file (CSV/XLSX, any column names) and this spec:

1. For each column in the raw file, find the best matching canonical field
   below by checking the field's `aliases` list (case-insensitive,
   punctuation/underscore-insensitive matching is fine — e.g. `Hire Date`,
   `hire-date`, and `HIREDATE` all match `employee_hire_date`).
2. Rename matched columns to their **canonical field name** exactly as
   written below.
3. Reformat values per the "Format" rules for each field (dates → ISO
   `YYYY-MM-DD`, booleans → `true`/`false`, decimals → plain numbers with no
   currency symbols or thousands separators).
4. Drop columns that don't map to anything in this schema and aren't needed
   — extra columns are ignored by the importer, so it's safe to leave
   unmapped columns out, or keep them if the user wants to preserve them.
5. Confirm all 5 **required** fields are present and non-null for every row.
   If any are missing entirely, stop and report which ones — don't
   guess/fabricate employee data.
6. Output a single flat table (CSV or XLSX) with one row per employee and
   canonical column headers.
7. Flag anything ambiguous (e.g. a column that could be `employee_id` or
   `employee_ssn`, or a status column with unexpected values) instead of
   silently choosing.

## File requirements

- **Format:** `.csv` or `.xlsx` through the import wizard (an `.xlsx` with
  several sheets prompts for one). A `.parquet` file that already uses the
  canonical names can be uploaded directly instead, with no mapping step.
- **Shape:** one row per employee, one header row, flat columns (no merged
  cells, no multi-row headers).
- **Size limit:** 500 MB for CSV/XLSX in the import wizard; 50 MB for a
  direct Parquet upload.
- **Encoding:** UTF-8 for CSV. Non-UTF-8 files fall back to Latin-1 with a
  warning when characters may be garbled.
- **Repeated headers:** the wizard renames repeats (`salary`, `salary_1`).
- **Uniqueness:** `employee_id` should be unique. If duplicates exist, the
  importer keeps the row with the most recent `employee_hire_date` (ties
  broken by higher `employee_gross_compensation`) and drops the rest — so
  it's best to dedupe upstream and not rely on this.

## Canonical fields

### Required

These five fields must be present and populated for every employee row.

| Field | Type | Description | Accepted source column names (aliases) |
|---|---|---|---|
| `employee_id` | string | Unique employee identifier — primary key across all simulation events | `empid`, `emp_id`, `id`, `employeeid`, `employee_number`, `emp_no`, `empno`, `employee_no`, `staff_id`, `staffid`, `worker_id`, `workerid` |
| `employee_birth_date` | date | Date of birth — drives age bands and age-based parameters | `dob`, `date_of_birth`, `birthdate`, `birth_date`, `dateofbirth`, `birth`, `bdate`, `born` |
| `employee_hire_date` | date | Original hire date — drives tenure and plan eligibility | `hire_date`, `hiredate`, `date_of_hire`, `dateofhire`, `start_date`, `startdate`, `hire`, `employment_date`, `employmentdate`, `date_hired` |
| `employee_gross_compensation` | decimal | Actual plan-eligible earnings for the plan year, as supplied by the sponsor; part-year for hires and leavers. See the notes on estimated annual pay below — drives comp growth and DC plan contributions | `salary`, `annual_salary`, `base_pay`, `gross_comp`, `compensation`, `base_salary`, `annualsalary`, `basepay`, `grosscomp`, `annual_compensation`, `annualcompensation`, `base_compensation`, `pay`, `wages`, `annualpay`, `annual_pay`, `total_comp`, `totalcomp` |
| `active` | boolean | Whether the employee is currently employed | `status`, `is_active`, `isactive`, `employment_status`, `employmentstatus`, `employed`, `current`, `active_flag`, `activeflag` |

### Optional

Populate when available — they unlock more accurate simulation. Missing
optional fields degrade gracefully (see "Behavior when fields are missing"
below); they don't block ingestion.

| Field | Type | Description | Accepted source column names (aliases) |
|---|---|---|---|
| `employee_ssn` | string | Synthetic SSN-style identifier (e.g. `SSN-00000001`) — **not a real SSN**; use as a secondary unique ID, never a live SSN. Truly optional: if omitted, the pipeline deterministically synthesizes one from `employee_id` (`SSN-` + a 9-digit hash), so leaving it out never blocks ingestion | `ssn`, `social_security`, `ssn_id`, `socialsecurity` |
| `employee_termination_date` | date | Termination date for separated employees; null for active employees. Any row with a termination date is left out of the simulation's starting workforce (`int_baseline_workforce`); without the column every row starts as active, whatever `active` says | `term_date`, `termination_date`, `separation_date`, `end_date`, `termdate`, `separationdate`, `enddate`, `exit_date`, `exitdate`, `date_terminated`, `dateterminated` |
| `employee_capped_compensation` | decimal | IRS 401(a)(17) capped compensation. Ingested but not used: the engine applies the IRS compensation limit itself | `capped_comp`, `cappedcomp`, `415_limit`, `irs_cap`, `plan_year_compensation`, `capped_compensation` |
| `employee_deferral_rate` | decimal | Current deferral rate as a decimal, `0.00`–`1.00` (e.g. `0.06` = 6%). A rate above 0 starts the employee enrolled at that rate; missing means 0% and not enrolled | `deferral_rate`, `deferralrate`, `deferral_pct`, `contribution_rate`, `contributionrate`, `deferral`, `deferral_percent` |
| `employee_contribution` | decimal | Total employee contribution dollar amount for the plan year. Ingested but not used today | `total_ee_contribution`, `ee_contribution`, `eecontribution`, `total_contribution`, `totalcontribution` |
| `pre_tax_contribution` | decimal | Pre-tax (traditional) 401(k) deferral amount. Ingested but not used today | `pre_tax`, `pretax`, `traditional_401k`, `traditional401k`, `pretax_contribution`, `pre_tax_deferral` |
| `roth_contribution` | decimal | Roth 401(k) after-tax deferral amount. Ingested but not used today | `roth`, `roth_401k`, `roth401k`, `roth_deferral` |
| `after_tax_contribution` | decimal | After-tax (non-Roth) contribution amount. Ingested but not used today | `after_tax`, `aftertax`, `after_tax_voluntary`, `aftertaxcontribution` |
| `employer_core_contribution` | decimal | Employer non-elective (core/profit-sharing) contribution amount. Not a simulation input; Census Analysis and the census tie-out report it | `er_core`, `ercore`, `non_elective`, `nonelective`, `employer_core`, `profit_sharing`, `profitsharing`, `core_contribution` |
| `employer_match_contribution` | decimal | Employer matching contribution amount. Not a simulation input; Census Analysis and the census tie-out report it | `er_match`, `ermatch`, `employer_match`, `matching`, `match_contribution`, `matchcontribution`, `employer_matching` |
| `eligibility_entry_date` | date | Plan entry date. Not a simulation input: the engine calculates eligibility from hire date + plan rules. Census Analysis and the census tie-out use it to count eligible employees | `entry_date`, `entrydate`, `eligibility_date`, `eligibilitydate`, `plan_entry`, `planentry`, `eligibility_entry` |
| `scheduled_hours_per_week` | decimal | Scheduled weekly hours. Blank counts as 40 hrs/wk for the employer match/core annual-hours rule (`int_employer_eligibility`); also drives the census part-time share (weekly hours x 52 < 1,000) and is the last source of an hourly rate | `hours_per_week`, `scheduled_hours`, `weekly_hours` |
| `hourly_rate` | decimal | Base hourly rate in dollars. The preferred way to give an hourly rate (see **Hourly rates** below) | `hourly_pay_rate`, `hourly_wage`, `rate_per_hour` |
| `hours_worked` | decimal | All paid hours in the census year, overtime included | `annual_hours_worked`, `paid_hours`, `hours_paid` |
| `auto_escalation_opt_out` | boolean | Per-employee opt-out of auto-escalation; defaults to `false` (participates) if omitted | *(no aliases — must match exactly)* |
| `eligibility_override` | boolean | Per-employee plan eligibility override: `true`=eligible, `false`=ineligible, omitted/null=unspecified (calculated normally) | *(no aliases — must match exactly)* |

The last two rows (`auto_escalation_opt_out`, `eligibility_override`) are not
in the import wizard's field list (`FIELDS`), so the wizard cannot map them.
They are read only from a directly uploaded Parquet file that already has
these exact column names. Every other row can be mapped in the wizard.

**Age and census eligibility.** Census employees are taken as given. Anyone past
the waiting period is eligible whatever
their age, and the plan's minimum age is not reapplied to them. The minimum age
applies to employees the simulation hires. New-hire ages start at 21, the highest
minimum age a plan may require, so no simulated hire is too young to become
eligible. Studio and config validation reject new-hire ages under 21.

## Value formatting rules

- **Dates:** prefer ISO 8601, `YYYY-MM-DD` (e.g. `2019-03-15`). The importer
  also accepts `YYYY/MM/DD`, `MM/DD/YYYY`, `DD/MM/YYYY`, `MM-DD-YYYY`,
  `DD-MM-YYYY` and `YYYYMMDD` (`CENSUS_DATE_FORMATS`), one format per column.
  If a column reads both month-first and day-first, the upload asks which.
  A non-blank value that does not parse stops the import with the column
  name; it never silently becomes null.
- **Booleans:** prefer literal `true` / `false`. The importer accepts
  `BOOLEAN_TRUE_ALIASES` (`true`, `t`, `yes`, `y`, `1`, `1.0`, `active`,
  `employed`, `enrolled`, `eligible`) and `BOOLEAN_FALSE_ALIASES` (`false`,
  `no`, `n`, `0`, `0.0`, `inactive`, `terminated`, `separated`,
  `ineligible`), case-insensitive; blank is null. Any other value (e.g.
  `Leave`) stops the import, so map other status strings to `true`/`false`
  first.
- **Decimals (compensation, contributions, rates):** plain numbers are
  safest. `$`, `€`, `£`, correctly placed thousands commas and parentheses
  for negatives are accepted; a `%` sign is not. `employee_deferral_rate` is
  a fraction of 1 (`0.06`, not `6`).
- **`employee_gross_compensation` holds actual plan-eligible earnings** for the
  plan year, exactly as the sponsor supplied them. Hires and leavers therefore
  show part-year pay, and full-year employees show a blend of pay before and
  after any raise. Load the value as received: do not annualize or adjust it by
  hand. Hours, full/part-time flags and bonus or overtime detail are rarely or
  never available, so they cannot be separated out.
- **Estimated annual pay.** The engine estimates an annual rate for active
  employees hired during the census year: earnings x days in the year / days
  employed. The census year is the latest hire year holding at least 1% of the
  file. Hires with under 30 days employed or no earnings get the median estimate
  of the other census-year hires. Everyone else keeps their earnings as their
  rate, so full-year pay runs slightly under year-end pay when raises land
  mid-year. Hours are not used, so seasonal work and unpaid leave are not
  detected. The received value is never changed.
- **Files that hold true annual rates:** set `setup.census_pay_basis: annual_rate`.
- **Hourly rates (#1230).** A minimum wage change needs an hourly rate for each
  hourly person. Give one of these per person; leave all of them blank for
  anyone who is not hourly:
  - `hourly_rate`: the rate as given. **Preferred.** Ask sponsors for it.
  - `hours_worked`: all paid hours in the census year. The rate is census-year
    pay / hours (under `annual_rate`, the rate prorated to the days employed).
    Overtime hours are not removed, and pay divided by all hours overstates the
    base rate for people paid overtime premium or bonuses, so some people just
    under a new minimum would be missed.
  - `scheduled_hours_per_week`: the rate is the annual pay rate / (hours x 52).
    Right only when census pay is an annual rate, not earnings.

  When a row fills more than one, `hourly_rate` wins, then `hours_worked`, then
  `scheduled_hours_per_week`, and the import says how many rows that affected.
  Hours are never inferred: a blank row means not hourly, and a minimum wage
  change never touches that person. A rate below $7.25 or above $500 an hour is
  flagged at import, does not stop the import, and leaves that person with no
  rate (bounds: `census_hourly_rate_min`/`census_hourly_rate_max` in
  `dbt/dbt_project.yml`). The import does not compare rates against the
  sponsor's own old minimum. Staging publishes the result as
  `census_hourly_rate` and `census_hourly_rate_source` on `stg_census_data` and
  `int_baseline_workforce`. A bridge census (roll-forward) writes each census
  employee's rate, moved with their pay, as `hourly_rate`.
- **IDs:** treat as strings even if numeric-looking (leading zeros must be
  preserved — don't let a spreadsheet tool strip them).

## Behavior when fields are missing (for context, not to reproduce)

- Missing `employee_ssn` → a deterministic placeholder is synthesized from
  `employee_id` (`SSN-` + a 9-digit hash), never a real SSN.
- Missing `employee_termination_date` → every row starts the simulation as
  active. The simulation's starting workforce is "no termination date"; the
  `active` flag is used by Studio's census reports (Census Analysis, tie-out,
  turnover), not to drop rows, so give leavers a termination date.
- Missing `employee_capped_compensation` → no effect; the column is not used.
- Missing `employee_deferral_rate` → everyone starts at 0%, not enrolled.
- Missing contribution dollar columns → no effect on the simulation; the
  match/core tie-out rows say the census has no data.
- Missing `auto_escalation_opt_out` → defaults to `false` (employee
  participates in auto-escalation).
- Missing `eligibility_override` → treated as unspecified; eligibility is
  calculated normally from hire date + waiting period.
- Missing `scheduled_hours_per_week` → employee is assumed full-time
  (40 hrs/week) for the employer annual-hours rule, and Studio cannot
  estimate a census part-time share.
- Missing all of `hourly_rate`, `hours_worked` and `scheduled_hours_per_week`
  → nobody has an hourly rate, so a run with a minimum wage stops with an error
  naming these columns.
- Missing `eligibility_entry_date` → no effect on the simulation, which
  always calculates eligibility from hire date + plan rules. Census Analysis
  counts every active employee as eligible, and the tie-out skips the
  eligible-count row.

## Example (minimal, required fields only)

```csv
employee_id,employee_birth_date,employee_hire_date,employee_gross_compensation,active
EMP_00001,1985-04-12,2015-06-01,95000.00,true
EMP_00002,1992-11-03,2021-01-15,72000.00,true
EMP_00003,1978-02-27,2008-09-01,110000.00,false
```

## Example (fuller, with common optional fields)

```csv
employee_id,employee_ssn,employee_birth_date,employee_hire_date,employee_termination_date,employee_gross_compensation,active,employee_deferral_rate,employer_match_contribution
EMP_00001,SSN-00000001,1985-04-12,2015-06-01,,95000.00,true,0.06,3200.00
EMP_00002,SSN-00000002,1992-11-03,2021-01-15,,72000.00,true,0.03,1500.00
EMP_00003,SSN-00000003,1978-02-27,2008-09-01,2024-05-30,110000.00,false,0.00,0.00
```
