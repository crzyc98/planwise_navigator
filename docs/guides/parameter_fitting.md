# Fitting parameters from census history (`planalign fit`)

**Issue #458** (Evidence loop I) — supersedes #443.

Every hazard and behavioural parameter in PlanAlign ships as a hand-set seed
value. That makes any projection ultimately "trust my assumptions."
`planalign fit` replaces those assumptions with **parameters estimated from the
client's own census history**, packaged with the provenance to prove where they
came from.

```bash
# Fit from 2-5 consecutive annual census snapshots
planalign fit data/history/ --output var/param_packs/acme-2024

# Apply the pack to a simulation (isolated DB, per the isolated-DB rule)
planalign simulate 2025-2029 --params var/param_packs/acme-2024 --database iso.duckdb
```

---

## Input: the snapshot directory

A directory of **2-5 consecutive annual census files** (`.parquet` or `.csv`),
in the same schema the simulator already consumes. The anonymizer (#449) output
satisfies it.

| Column | Required | What it unlocks |
|---|---|---|
| `employee_id` | ✅ | cohort linking — the whole method |
| `employee_birth_date` | ✅ | age band and age segment |
| `employee_hire_date` | ✅ | tenure band, new-hire cohort |
| `employee_gross_compensation` | ✅ | level, income segment, merit |
| `employee_termination_date` / `active` | | new-hire termination rate |
| `employee_deferral_rate` | | deferral rates, escalation |
| `employee_enrollment_date` | | enrollment and opt-out behaviour |
| `level_id` | | promotions measured instead of inferred |

The year of each file comes from a `snapshot_year` column when present,
otherwise from a single unambiguous four-digit year in the filename
(`census_2023.parquet`). Non-consecutive years are rejected: the cohort diff
assumes a one-year step.

**Supply `level_id` if you have it.** Without it, level is derived from
compensation banding (the same rule `int_baseline_workforce` uses), so any
merit raise that crosses a band boundary reads as a promotion and the fitted
promotion hazard is an upper bound. The fit report warns when this happens.

---

## What gets fitted

### Hazards — `base × age_mult × tenure_mult × level_factor`

Termination and promotion are fitted in the simulator's own functional form
with an exposure-weighted iterative proportional fit (a Poisson log-linear
model with the level factor as a fixed offset). Output lands in
`config_termination_hazard_*.csv` and `config_promotion_hazard_*.csv`.

Exposure for a year-`t` rate is the population **active at the end of year
`t-1`**, in its year `t-1` bands — the band is known before the event resolves,
exactly as the simulator applies a hazard. New hires are therefore excluded by
construction, matching the E077 cohort split; their termination rate is fitted
separately from the new-hire cohort.

### Compensation

`merit_base` per job level (into `comp_levers.csv`), as the median
year-over-year compensation growth of employees who stayed and were **not**
promoted, net of the configured COLA. Promotions are excluded — their raise is
modelled separately.

### Enrollment and deferral

| Parameter | Source population |
|---|---|
| `enrollment.voluntary_enrollment.base_rates_by_age` / `income_multipliers` | non-participants auto-enrollment did not cover |
| `enrollment.auto_enrollment.opt_out_rates.target` | first-year non-participation (proxy — see below) |
| `default_deferral_rates.csv` | starting rate of the newly enrolled |
| `deferral_auto_escalation.increment_amount` | participants who raised their rate |

Which population is at risk depends on auto-enrollment in the base config:

| `auto_enrollment` | voluntary exposure | opt-out fit |
|---|---|---|
| disabled | continuing + new hires | not applicable |
| enabled, `new_hires_only` | continuing only | new hires (proxy) |
| enabled, all eligible | nothing (flagged unfittable) | everyone (proxy) |

**The opt-out fit is a proxy.** A census records who is participating, not who
was auto-enrolled and then opted out. The report says so loudly.

### Scalars

`workforce.total_termination_rate`, `workforce.new_hire_termination_rate`, and
`simulation.target_growth_rate` (observed year-over-year active headcount).

---

## What does *not* get fitted

The report's **"Not fitted — defaults retained"** section is the point of the
exercise, not an apology. It always names:

- `compensation.cola_rate` — a policy input the sponsor sets, not a behaviour
  to recover. Held at the configured value; merit absorbs the remainder.
- `level_discount_factor` / `min_level_discount_multiplier` /
  `level_dampener_factor` — level is assigned from compensation banding, so a
  level effect cannot be separated from the banding itself. Held fixed and used
  as the hazard's offset.
- `deferral_match_response.*` — identifying a match response needs a change in
  the match formula inside the observation window; a census carries deferral
  rates but not the plan's match schedule.
- `voluntary_enrollment.job_level_multipliers.*` — near-collinear with the
  income segment.

Plus anything the supplied columns cannot support (no deferral column → no
deferral fit, and so on).

---

## Small cells never become parameters

Every fitted value is a credibility blend of the data and a prior — **the
current seed or config value**, per #443:

```
Z = exposure / (exposure + k)
fitted = Z × observed + (1 − Z) × prior
```

`--credibility-k` (default 200) is the exposure at which data and prior carry
equal weight. `--min-exposure` (default 50) marks a cell `pooled`, flagged in
the report with ⚠️. A cell with no exposure keeps the prior outright.

Every row of the report carries its exposure, its credibility weight, and its
basis (`observed` / `blended` / `pooled` / `prior`), so a number that looks
surprising can be checked against the evidence behind it.

---

## The parameter pack

```
<pack>/
  manifest.json      pack id, fingerprint, fit date, per-file SHA-256, unfittable list
  parameters.yaml    config fragment, deep-merged over the base config
  seeds/*.csv        drop-in replacements, same schema as the seeds they replace
  fit_report.md      evidence for every number, and what was not fitted
```

The fingerprint is a SHA-256 over the config fragment, every seed byte, and the
source-snapshot digest. It is deterministic: fitting the same snapshots twice
with the same options produces the same fingerprint.

### Applying a pack

`planalign simulate --params <pack>` **never modifies the repository.** It:

1. deep-merges `parameters.yaml` over the base config into an effective config
   under `var/param_packs/<pack_id>/`;
2. builds an overlay dbt project there whose `seeds/` is a private copy with the
   pack's CSVs swapped in — models and macros are symlinked to the real project;
3. hands the orchestrator an ordinary `--config` and `--dbt-project-dir`.

Nothing downstream of config loading changes. `--params` and
`--dbt-project-dir` cannot be combined: the pack needs its own seed overlay.

### Provenance

The effective config carries a `param_pack` block, which
`run_metadata` records alongside the existing Feature 109 columns:

```bash
duckdb iso.duckdb "SELECT run_timestamp, param_pack_id,
  substr(param_pack_fingerprint,1,12) AS pack_fp,
  substr(param_pack_source_digest,1,12) AS sources
  FROM run_metadata ORDER BY run_timestamp DESC"
```

The block is an untyped config extra that `to_dbt_vars` ignores, so it records
*which evidence produced this run* without disturbing the config fingerprint.

If a pack's files are edited after fitting, the fingerprint no longer verifies
and both `--params` and `verify_pack()` say so — the run proceeds, but the
provenance is marked unreliable.

---

## Verifying a fit

The round-trip test (`tests/test_parameter_fitting.py::TestRoundTrip`) is the
grading harness: `tests/fixtures/synthetic_census.py` evolves a population with
rates the test chose, writes a snapshot per year, and asserts `fit` recovers
them within tolerance — independently of the simulator.

```bash
pytest tests/test_parameter_fitting.py -q
```

To check a pack against a real population, apply it in an **isolated** database
(never the shared dev DB) and compare the next actual census year:

```bash
planalign simulate 2024 --params var/param_packs/acme-2024 --database /tmp/fitcheck.duckdb
duckdb /tmp/fitcheck.duckdb "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = 2024"
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `--output` / `-o` | `var/param_packs/<pack_id>` | pack destination |
| `--config` / `-c` | `config/simulation_config.yaml` | config supplying the priors |
| `--seeds-dir` | `dbt/seeds` | seeds supplying bands and priors |
| `--credibility-k` | `200` | exposure at which data and prior tie |
| `--min-exposure` | `50` | below this a cell is flagged thin |
| `--pack-id` | `fit-<years>-<timestamp>` | pack name |
| `--notes` | — | free text recorded in the manifest |
| `--force` | off | replace an existing pack directory |

Exit codes: `2` bad arguments, `3` unreadable snapshots, `4` output refused.
