# Census File Format Guide (LLM Reformatting Reference)

This document is meant to be handed to an LLM together with a raw/arbitrary
census export. The LLM should use it to map the source file's columns onto
the canonical schema below and produce a cleaned CSV or XLSX file ready for
upload to Fidelity PlanAlign Engine.

Source of truth in the codebase: `planalign_api/services/census_schema.py`
(canonical fields + aliases) and `dbt/models/staging/stg_census_data.sql`
(how columns are cast and defaulted once ingested). If those files and this
doc ever disagree, the code wins — but this doc is kept in sync with them.

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

- **Format:** `.csv` or `.xlsx` (single sheet). Internally converted to
  Parquet — you may also hand-produce a `.parquet` file directly if working
  outside the upload UI.
- **Shape:** one row per employee, one header row, flat columns (no merged
  cells, no multi-row headers).
- **Size limit:** 100 MB.
- **Encoding:** UTF-8 for CSV.
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
| `employee_gross_compensation` | decimal | **Annual salary rate** (not prorated/YTD earnings) — drives comp growth and DC plan contributions | `salary`, `annual_salary`, `base_pay`, `gross_comp`, `compensation`, `base_salary`, `annualsalary`, `basepay`, `grosscomp`, `annual_compensation`, `annualcompensation`, `base_compensation`, `pay`, `wages`, `annualpay`, `annual_pay`, `total_comp`, `totalcomp` |
| `active` | boolean | Whether the employee is currently employed | `status`, `is_active`, `isactive`, `employment_status`, `employmentstatus`, `employed`, `current`, `active_flag`, `activeflag` |

### Optional

Populate when available — they unlock more accurate simulation. Missing
optional fields degrade gracefully (see "Behavior when fields are missing"
below); they don't block ingestion.

| Field | Type | Description | Accepted source column names (aliases) |
|---|---|---|---|
| `employee_ssn` | string | Synthetic SSN-style identifier (e.g. `SSN-00000001`) — **not a real SSN**; use as a secondary unique ID, never a live SSN. Truly optional: if omitted, the pipeline deterministically synthesizes one from `employee_id` (`SSN-` + a 9-digit hash), so leaving it out never blocks ingestion | `ssn`, `social_security`, `ssn_id`, `socialsecurity` |
| `employee_termination_date` | date | Termination date for separated employees; null for active employees | `term_date`, `termination_date`, `separation_date`, `end_date`, `termdate`, `separationdate`, `enddate`, `exit_date`, `exitdate`, `date_terminated`, `dateterminated` |
| `employee_capped_compensation` | decimal | IRS 401(a)(17) capped compensation; defaults to gross compensation if omitted | `capped_comp`, `cappedcomp`, `415_limit`, `irs_cap`, `plan_year_compensation`, `capped_compensation` |
| `employee_deferral_rate` | decimal | Current deferral rate as a decimal, `0.00`–`1.00` (e.g. `0.06` = 6%) | `deferral_rate`, `deferralrate`, `deferral_pct`, `contribution_rate`, `contributionrate`, `deferral`, `deferral_percent` |
| `employee_contribution` | decimal | Total employee contribution dollar amount for the plan year | `total_ee_contribution`, `ee_contribution`, `eecontribution`, `total_contribution`, `totalcontribution` |
| `pre_tax_contribution` | decimal | Pre-tax (traditional) 401(k) deferral amount | `pre_tax`, `pretax`, `traditional_401k`, `traditional401k`, `pretax_contribution`, `pre_tax_deferral` |
| `roth_contribution` | decimal | Roth 401(k) after-tax deferral amount | `roth`, `roth_401k`, `roth401k`, `roth_deferral` |
| `after_tax_contribution` | decimal | After-tax (non-Roth) contribution amount | `after_tax`, `aftertax`, `after_tax_voluntary`, `aftertaxcontribution` |
| `employer_core_contribution` | decimal | Employer non-elective (core/profit-sharing) contribution amount | `er_core`, `ercore`, `non_elective`, `nonelective`, `employer_core`, `profit_sharing`, `profitsharing`, `core_contribution` |
| `employer_match_contribution` | decimal | Employer matching contribution amount | `er_match`, `ermatch`, `employer_match`, `matching`, `match_contribution`, `matchcontribution`, `employer_matching` |
| `eligibility_entry_date` | date | Override for plan eligibility entry date; if present, used instead of the calculated hire-date + waiting-period date | `entry_date`, `entrydate`, `eligibility_date`, `eligibilitydate`, `plan_entry`, `planentry`, `eligibility_entry` |
| `scheduled_hours_per_week` | decimal | Scheduled weekly hours; omit for full-time (defaults to 40 hrs/wk downstream) | `hours_per_week`, `scheduled_hours`, `weekly_hours` |
| `auto_escalation_opt_out` | boolean | Per-employee opt-out of auto-escalation; defaults to `false` (participates) if omitted | *(no aliases — must match exactly)* |
| `eligibility_override` | boolean | Per-employee plan eligibility override: `true`=eligible, `false`=ineligible, omitted/null=unspecified (calculated normally) | *(no aliases — must match exactly)* |

## Value formatting rules

- **Dates:** ISO 8601, `YYYY-MM-DD` (e.g. `2019-03-15`). Other formats may
  fail to parse and silently become null — always normalize to ISO before
  producing output.
- **Booleans:** prefer literal `true` / `false`. The importer will also cast
  `1`/`0` and similar SQL-boolean-castable values for `active`, but literal
  `true`/`false` is safest. For the `active`/`status` column specifically,
  if the source has a **status string** (e.g. `Active`, `Terminated`,
  `Leave`) instead of a boolean, map it explicitly: anything meaning
  currently employed → `true`, anything else → `false`. Only the literal
  string `active` (case-insensitive) is treated as "employed" when a status
  column is used as-is instead of a boolean — so always convert status
  strings to a true/false `active` column rather than passing status text
  straight through.
- **Decimals (compensation, contributions, rates):** plain numbers, no `$`,
  no thousands separators, no `%` sign. `employee_deferral_rate` is a
  fraction of 1 (`0.06`, not `6`).
- **`employee_gross_compensation` is always the annual salary rate**, not
  year-to-date or prorated earnings — if the source only provides YTD pay
  and a hire/term date, do not attempt to back into an annual rate by
  simple extrapolation; flag it for the user instead, since the pipeline
  prorates the annual rate itself using hire/termination dates.
- **IDs:** treat as strings even if numeric-looking (leading zeros must be
  preserved — don't let a spreadsheet tool strip them).

## Behavior when fields are missing (for context, not to reproduce)

- Missing `employee_ssn` → a deterministic placeholder is synthesized from
  `employee_id` (`SSN-` + a 9-digit hash), never a real SSN.
- Missing `employee_termination_date` or `active` → all employees are
  treated as currently active.
- Missing `employee_capped_compensation` → defaults to
  `employee_gross_compensation`.
- Missing `auto_escalation_opt_out` → defaults to `false` (employee
  participates in auto-escalation).
- Missing `eligibility_override` → treated as unspecified; eligibility is
  calculated normally from hire date + waiting period.
- Missing `scheduled_hours_per_week` → employee is assumed full-time
  (40 hrs/week).
- Missing `eligibility_entry_date` → eligibility entry date is calculated
  from hire date + plan waiting period.

## Example (minimal, required fields only)

```csv
employee_id,employee_birth_date,employee_hire_date,employee_gross_compensation,active
EMP_00001,1985-04-12,2015-06-01,95000.00,true
EMP_00002,1992-11-03,2021-01-15,72000.00,true
EMP_00003,1978-02-27,2008-09-01,110000.00,false
```

## Example (fuller, with common optional fields)

```csv
employee_id,employee_ssn,employee_birth_date,employee_hire_date,employee_termination_date,employee_gross_compensation,active,employee_deferral_rate,employer_match_contribution,scheduled_hours_per_week
EMP_00001,SSN-00000001,1985-04-12,2015-06-01,,95000.00,true,0.06,3200.00,40
EMP_00002,SSN-00000002,1992-11-03,2021-01-15,,72000.00,true,0.03,1500.00,40
EMP_00003,SSN-00000003,1978-02-27,2008-09-01,2024-05-30,110000.00,false,0.00,0.00,40
```
