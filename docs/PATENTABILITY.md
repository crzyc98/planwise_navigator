# Patentability Analysis: Fidelity PlanAlign Engine

*Analysis date: February 2026*

---

## Executive Summary

Three inventions in PlanAlign Engine were evaluated for patentability. The **algebraic workforce solver** has the strongest novelty position with low prior art risk. The **configuration-drift checkpoint recovery** system is a solid secondary candidate. The **cross-platform deterministic RNG** is weaker due to prior art proximity and an implementation mismatch.

| Rank | Invention | Key File(s) | Novelty Risk | Recommendation |
|------|-----------|-------------|--------------|----------------|
| 1 | Algebraic Workforce Solver | `dbt/models/intermediate/int_workforce_needs.sql` | Low | **File first** |
| 2 | Config-Drift Checkpoint Recovery | `planalign_orchestrator/checkpoint_manager.py`, `recovery_orchestrator.py` | Low-Medium | **File second** |
| 3 | Cross-Platform Deterministic RNG | `dbt/macros/utils/rand_uniform.sql`, `planalign_orchestrator/generators/base.py` | Medium-High | Defer or combine |

---

## Candidate 1: Single-Rounding Algebraic Workforce Solver

**Epic**: E077 — Bulletproof Workforce Growth Accuracy
**Location**: `dbt/models/intermediate/int_workforce_needs.sql` lines 89-186

### What It Does

Given a starting workforce, a target growth rate, and two employee cohorts with different attrition rates (experienced employees vs. new hires), the algorithm computes exact integer headcounts for hires and terminations with **mathematically guaranteed zero reconciliation error**.

### The Algorithm

```
Input: N_start, growth_rate, exp_term_rate, nh_term_rate
       experienced_count, prior_new_hire_count

Step 1: target_ending = ROUND(N_start * (1 + growth_rate))        [banker's rounding]
Step 2: exp_terms = FLOOR(experienced * exp_rate + prior_nh * nh_rate)  [conservative]
Step 3: survivors = N_start - exp_terms
Step 4: net_hires = target_ending - survivors
Step 5: total_hires = CEILING(net_hires / (1 - nh_term_rate))     [ensure enough hires]
Step 6: implied_nh_terms = total_hires - net_hires                 [residual, not rounded]
Step 7: ASSERT N_start + total_hires - exp_terms - implied_nh_terms == target_ending

Invariant: reconciliation_error = 0 (algebraically guaranteed by residual in Step 6)
```

The key insight is that only 3 of the 4 quantities (target, exp_terms, total_hires, nh_terms) are independently rounded. The 4th (implied new-hire terminations) is computed as a **residual**, which algebraically forces the balance equation to hold exactly.

### Why It Matters

- Standard workforce planning uses either stochastic simulation (Monte Carlo) or general-purpose integer programming solvers
- This is a **closed-form algebraic solution** — no iteration, no solver, no rounding error
- The strategic rounding hierarchy (banker's / FLOOR / CEILING / residual) is applied at specific computation points to minimize cumulative error while maintaining exact balance
- Includes 4 feasibility guards and a separate RIF (reduction-in-force) branch for negative growth

### Prior Art Search

| Prior Art | How It Differs |
|-----------|---------------|
| **US8639551B1** (HP, 2006) — Workforce resource planning with probability distributions of integer random variables | Probabilistic gap analysis; does not solve for exact integer quantities with zero error |
| **US20120016710A1** (HP, 2010, abandoned) — Simulate workforce supply/demand with attrition/hiring rates | Monte Carlo simulation; inherently has variance, does not guarantee exact balance |
| **US8386300B2** (Optimization Technologies, 2010) — Agent-based strategic workforce planning | Agents make stochastic career decisions; fundamentally different approach |
| **US20090271240A1** (Infosys, 2008, abandoned) — Stochastic programming for headcount planning | Cost-minimization optimization formulation, not closed-form algebraic solver |
| **Integer programming for workforce planning** (European J. of Operational Research, 2014) | Uses general-purpose MIP solvers with binary variables; our approach is closed-form |
| **Markov chain manpower planning** (various academic) | Produces expected values, not exact integers; stochastic by nature |

**Assessment**: No prior art found using the specific combination of (a) dual-cohort algebraic decomposition, (b) strategically ordered rounding operations, and (c) guaranteed zero reconciliation error via residual calculation.

### Preliminary Patent Claims

**Independent Claim 1 (Method):**

A computer-implemented method for determining exact integer workforce planning quantities across multiple employee cohorts, comprising:

(a) receiving, by a processor, a starting workforce count, a target growth rate, a first attrition rate for experienced employees, and a second attrition rate for new hires;

(b) computing a target ending workforce by applying banker's rounding to the product of the starting workforce and one plus the target growth rate;

(c) computing expected experienced terminations by applying floor rounding to the product of the experienced workforce count and the first attrition rate;

(d) computing a survivor count by subtracting the floor-rounded experienced terminations from the starting workforce;

(e) computing a net hire requirement by subtracting the survivor count from the banker's-rounded target;

(f) computing a total hire count by applying ceiling rounding to the quotient of the net hire requirement and one minus the second attrition rate;

(g) computing implied new-hire terminations as the residual difference between the total hire count and the net hire requirement, wherein the residual calculation algebraically guarantees that starting workforce plus total hires minus experienced terminations minus implied new-hire terminations equals the target ending workforce exactly;

(h) validating at least one feasibility constraint prior to computing the total hire count; and

(i) outputting the total hire count, experienced terminations, and implied new-hire terminations as integer quantities with zero reconciliation error.

**Dependent Claim 2:**

The method of claim 1, further comprising: detecting that the net hire requirement is non-positive and entering a reduction-in-force branch that sets total hires to zero and computes additional forced terminations as the absolute value of the net hire requirement.

**Dependent Claim 3:**

The method of claim 1, wherein the feasibility constraints include at least: (i) the second attrition rate is less than 0.99; (ii) the absolute growth rate does not exceed 1.0; (iii) the total hire count does not exceed a threshold proportion of starting workforce; and (iv) the implied new-hire terminations are non-negative and do not exceed total hires.

**Dependent Claim 4:**

The method of claim 1, wherein the method is implemented as a declarative SQL transformation within a data transformation framework, and the integer quantities are materialized as database records for consumption by downstream event-generation models.

**Independent Claim 5 (System):**

A workforce simulation system comprising: a processor; a database storing workforce state records; and a workforce planning module configured to execute the method of claim 1 for each simulation year in a multi-year simulation, wherein each year's starting workforce is derived from the prior year's computed ending workforce.

---

## Candidate 2: Configuration-Drift-Aware Checkpoint Recovery

**Location**: `planalign_orchestrator/checkpoint_manager.py`, `planalign_orchestrator/recovery_orchestrator.py`

### What It Does

A checkpoint/recovery system for multi-year simulations that captures SHA256 hashes of the simulation configuration at checkpoint time and **refuses to resume** if parameters have changed — preventing subtle compounding errors when Year N+1 depends on Year N state.

### Implementation Detail

**At checkpoint creation** (`checkpoint_manager.py:46-73`):
1. Computes SHA256 hash of `simulation_config.yaml`
2. Captures per-table row counts filtered by simulation year
3. Captures aggregate financial metrics (compensation totals, contribution totals, event distributions)
4. Computes an integrity hash (SHA256 of the entire checkpoint payload, excluding timestamps)
5. Persists via atomic write-and-rename with gzip compression

**At resume** (`recovery_orchestrator.py:96-133`):
1. Recomputes current config hash
2. Compares against stored hash — raises `ConfigurationDriftError` if different
3. Validates checkpoint version compatibility
4. Validates database row counts match checkpoint expectations
5. Validates data quality metrics (non-negative compensation, valid employee counts)
6. Only resumes if ALL checks pass

### Why It Matters

Most checkpoint systems simply save and restore state. This system validates the **assumptions** behind the checkpoint — specifically that the simulation parameters haven't changed. In a multi-year iterative simulation where Year N+1 depends on Year N state, a mid-run parameter change produces results that are plausible but silently wrong, with errors compounding across years.

### Prior Art Search

| Prior Art | How It Differs |
|-----------|---------------|
| **Terraform drift detection** | Detects infrastructure state drift; offers remediation rather than refusing to continue |
| **python-checkpointing** (GitHub) | Hashes function code to detect staleness; operates on code, not configuration parameters |
| **US9069782B2** — VM checkpoint with integrity validation | Validates that checkpoint data hasn't been corrupted/tampered, not that config is consistent |
| **Snakemake/Nextflow** workflow engines | Re-execute on input file changes (timestamps); don't validate configuration parameters at checkpoint boundaries |
| **V2: Configuration Drift in Python** (arXiv 2019) | Detects environment/dependency drift, not simulation parameter drift |
| **LangGraph durable execution** | Standard checkpoint/resume without any configuration validation |

**Assessment**: Individual components (hashing, checkpointing, validation) are well-known, but the specific combination applied to multi-year iterative simulation with compounding-error prevention is not found in prior art.

### Preliminary Patent Claims

**Independent Claim 1 (Method):**

A computer-implemented method for ensuring simulation integrity in a multi-year iterative simulation system, comprising:

(a) at checkpoint creation for simulation year N:
  - (i) computing a configuration fingerprint by hashing the contents of a simulation configuration file;
  - (ii) capturing database state metrics including per-table row counts filtered by simulation year;
  - (iii) capturing validation metrics including aggregate financial totals and event-type distributions;
  - (iv) computing an integrity hash over the combined checkpoint payload; and
  - (v) persisting the checkpoint payload with atomic write-and-rename;

(b) at simulation resumption:
  - (i) computing a current configuration fingerprint using the same hashing method;
  - (ii) comparing the current fingerprint against the stored checkpoint fingerprint;
  - (iii) if the fingerprints differ, refusing to resume and raising a configuration drift error;
  - (iv) if the fingerprints match, further validating that current database state matches the stored database state metrics; and
  - (v) resuming simulation from year N+1 only if all validations pass.

**Dependent Claim 2:**

The method of claim 1, wherein the integrity hash is computed by serializing the checkpoint payload as a deterministic JSON string with sorted keys, excluding timestamp fields, and applying SHA-256 hashing.

**Dependent Claim 3:**

The method of claim 1, further comprising: scanning available checkpoints in reverse chronological order to find the latest year whose checkpoint passes all validation checks.

**Dependent Claim 4:**

The method of claim 1, wherein the simulation is a workforce simulation in which year N+1 state depends on year N state, such that a configuration change between checkpoint and resume would produce compounding errors across subsequent years.

---

## Candidate 3: Cross-Platform Deterministic RNG (Weaker)

**Location**: `dbt/macros/utils/rand_uniform.sql`, `planalign_orchestrator/generators/base.py` lines 334-357

### What It Does

Generates reproducible pseudo-random values for workforce event selection using a composite hash key: `(seed|employee_id|year|event_type[|salt])`, normalized to [0, 1) via `(hash % 2147483647) / 2147483647.0`.

### Implementation Caveat

The SQL and Python implementations use **different hash functions**:
- SQL: DuckDB native `HASH()` function
- Python: `hashlib.md5()`

These produce different values for the same input. Since Epic E024 simplified the system to SQL-only mode, the Python path may not be actively exercised, weakening the "cross-platform synchronization" claim.

### Prior Art

Hash-based deterministic PRNG is well-established. Databricks Labs Data Generator uses a similar `hash_fieldname` approach. Game engines commonly solve cross-platform determinism by shipping identical PRNG implementations.

**Assessment**: The composite key design is domain-specific but likely viewed as an obvious arrangement of known techniques. Not recommended as a standalone patent filing.

### Preliminary Claim (if pursued)

A computer-implemented method for generating reproducible pseudo-random event selections in a workforce simulation, comprising: (a) constructing a composite hash key by concatenating a global random seed, an employee identifier, a simulation year, and an event type identifier; (b) applying a hash function to produce a hash value; (c) normalizing to [0, 1) via modular arithmetic with a large prime; (d) comparing against a hazard probability to determine event occurrence.

---

## Recommended Next Steps

1. **Engage a patent attorney** to refine claims for Candidate 1 (algebraic solver)
2. **Conduct formal freedom-to-operate search** through a patent search firm
3. **File provisional application** for Candidate 1 to establish priority date
4. **Evaluate Candidate 2** for separate filing or combination with Candidate 1

**Disclaimer**: This analysis identifies technical novelty and prior art landscape. Formal patentability opinions require a registered patent attorney/agent who can assess legal standards (35 U.S.C. 101/102/103) with professional judgment.
