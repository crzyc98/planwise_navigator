# First-year optimizer screening feasibility (#836)

## Plan and implementation boundary

Measure a paired, fixed candidate set through the existing optimizer's
the private `_evaluate_candidate_values` / `ScenarioRunPool` / `run_seed_worker` path before
changing production search. Preserve the simulation seed and all undeclared
inputs. Run a fresh full-horizon reference, a fresh first-year screen, and
fresh full-horizon reruns of the selected candidates. Use the same worker
limit and isolated databases for every stage.

The experiment conservatively retains feasible, uncertain, and borderline
screen results plus a deterministic audit sample. It evaluates feasibility
loss, frontier retention, best-objective loss, exact full-result replay,
actual pool wall time, evaluation count, and sampled process-tree RSS.
Screen results are research evidence and cannot be promoted as optimizer
recommendations. The existing optimizer keeps its exact default behavior.

Before running, the minimum useful speedup was set to **1.5x**, with zero
observed rejection of full-horizon feasible designs and exact replay of
retained full results. Three complete repetitions are required even to
recommend an expanded benchmark. A failed cost or quality gate is a NO-GO
for the tested policy/workload; passing this small experiment would not
authorize production rollout.

## Initial experiment

The pilot uses `tests/fixtures/optimizer_screening.yaml` and the existing
150-row synthetic invariant census. The baseline requests 2025–2027, seed
113435436, 10% existing-employee turnover, 15% new-hire turnover, an early
2015 enrollment cutoff, and delayed annual escalation. The complete eight
design grid crosses:

- Eligibility waiting period: 0 or 365 days.
- Enrollment scope: new hires or all eligible employees.
- Auto-escalation: disabled or enabled.

The objectives minimize terminal-year employer plan cost and maximize
terminal-year average deferral rate, with participation at least 65%.
Screen metrics refer to 2025; full metrics refer to 2027. Employer cost is an
annual metric, not cumulative cost across three years. Every candidate uses
the same baseline seed. Single-objective quality can also be calculated from
these same full results without any additional simulations.

Run from the repository root:

```bash
source .venv/bin/activate
PYTHONPATH=. python scripts/benchmark_optimizer_screening.py \
  --spec tests/fixtures/optimizer_screening.yaml \
  --census-csv tests/fixtures/invariant_census.csv \
  --output var/screening-benchmark/paired-01 \
  --candidates 8 --repetitions 1 --max-simulations 24 --parallel 2
```

This is a single-repetition development pilot, not a client-scale performance
claim. It is sufficient to identify that the tested screen removes no work;
it cannot establish general performance or false-negative rates across
censuses, seeds, or thresholds. Near-boundary constraints, missing evidence,
failed validation, and late-improving designs are also covered by focused
regression tests; they are not additional measured production workloads.

## Pilot results: NO-GO for this workload

Measured on 2026-10-14 with two workers, Python 3.12.11, DuckDB 1.1.3,
dbt-core 1.9.11, and dbt-duckdb 1.9.6 on macOS arm64. This used the
implementation branch based on main `289bf84fac2f280b90803334aff47f2f0b4c4adc`.
The local DuckDB version differs from the playbook's newer documented stack;
these timings must not be treated as a refreshed client-scale baseline for
that stack. No dependencies were installed for this pilot.

| Stage | Evaluations | Pool wall seconds | Sampled peak RSS MiB |
|---|---:|---:|---:|
| Full 2025–2027 reference | 8 | 284.20 | 1001.3 |
| First-year screen | 8 | 183.33 | 1030.1 |
| Retained full reruns | 8 | 285.32 | 1202.4 |

The staged strategy took **468.65 seconds**, versus **284.20 seconds** for
the reference: **0.61x speedup**, or approximately **65% more wall time**.
Individual screens took 45.1–46.1 seconds; full reference evaluations took
69.1–73.9 seconds. All 24 evaluations completed successfully.

Every first-year design passed the participation constraint and remained on
the first-year Pareto frontier. All eight therefore needed full validation;
screening removed no simulation work. Full feasibility and frontier retention
were 100%, and every retained full result replayed exactly. Evaluating only
the cost objective on these same ledgers also retained the best objective,
with zero objective loss; that analysis required no extra simulations.

**Decision: do not add a production first-year screening mode based on this
evidence.** It missed the prespecified 1.5x cost gate. This single-repetition
pilot does not establish a general NO-GO for multi-fidelity methods; it shows
that a selective and substantially cheaper signal must be demonstrated before
implementing them here. The proposed 75–80% pruning did not occur in this
workload, and the proposed 4–8x speedup was not observed.

The initial pilot artifacts are `benchmark.json` and `report.md` under the
ignored output directory. `analysis.json` and `analysis.md` add the derived
single-objective quality check without modifying the initial measurements.
The shipped harness includes that check and richer code/environment provenance
in future runs. Full databases, input artifacts, and worker logs remain
ignored under `var/`; this document contains only aggregate synthetic results.

## Reconsideration criteria

If a future workload has a demonstrably selective screen, run at least three
complete repetitions at the same worker limit and expand to both objective
modes, near-threshold cost and participation constraints, representative
client-scale censuses, and multiple simulation seeds. Each new hypothesis
needs gates set before observing its results. Distinguish fixed-candidate
evaluation economics from changes to the adaptive search's sampling path.
Candidate-specific ensembles, a learned surrogate, and a production screening
mode require separately scoped work only after supporting evidence.
