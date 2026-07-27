# Research: Edge-Configuration Regression Matrix

## R1 — Existing simulation harness and isolation

- Decision: Build each case through ConstructionSpec and build_orchestrator(...).orchestrator.execute_multi_year_simulation, with a unique DuckDB path from pytest tmp_path_factory.
- Rationale: Feature 113 already proves this path honors DATABASE_PATH, uses dbt with one thread, preserves simulation errors, and avoids the shared development database. Reusing it satisfies FR-004 and FR-010.
- Alternatives considered: Direct dbt model execution was rejected because it can omit orchestrator state setup; the shared dbt/simulation.duckdb was rejected by repository policy.

## R2 — Scenario representation

- Decision: Use a frozen case descriptor containing a stable name, config path, census path, start/end years, boundary description, fixture selectors, and an assertion kind. Keep the catalog append-only with exactly four entries.
- Rationale: Explicit descriptors make the four-case scope machine-checkable and make horizons/config boundaries reviewable.
- Alternatives considered: Four independent test modules were rejected because they duplicate setup/diagnostics; one opaque YAML file was rejected because assertions need readable typed behavior.

## R3 — Targeted assertion source

- Decision: Query completed fct_workforce_snapshot and fct_yearly_events, plus the existing employer-match output relation where needed, returning only violations and bounded samples.
- Rationale: These are existing simulation outputs used by Feature 113 and the relevant feature contracts. Targeted projections avoid byte-identical snapshots while failing the seeded mutations with employee/year evidence.
- Alternatives considered: Full database snapshots and event-history equality are already covered by Feature 113 and are explicitly out of scope here; unit-only config tests cannot detect runtime SQL regressions.

## R4 — Fixture boundaries

- Decision: Validate every case fixture before simulation. Each fixture has labeled employees on both sides of its boundary; missing groups are setup failures.
- Rationale: This prevents an empty target population from producing a vacuous business-rule pass.
- Alternatives considered: Inferring groups from simulation output was rejected because a broken cutoff could make the fixture appear valid; aggregate-only counts lose affected-employee diagnostics.

## R5 — Failure and CI contract

- Decision: Separate fixture setup, simulation execution, and behavioral assertion phases. Do not assert against a partial database. On assertion failure, report case, boundary, expected/observed values, and at most 20 affected records; preserve failed DuckDB files.
- Rationale: This matches Feature 113's SimulationRun pattern and the repository's transparency/isolation requirements.
- Alternatives considered: Treating all failures as ordinary assertions was rejected because partial databases create misleading diagnostics; deleting failed databases was rejected because developers need debugging artifacts.

## R6 — Runtime and CI

- Decision: Register edge_config_matrix, retain the integration marker, run one dedicated CI job with a bounded timeout and failure-only artifact upload, and document pytest -m edge_config_matrix -v.
- Rationale: A separate marker keeps Feature 113 as the single source for general invariant/determinism coverage and makes the five-minute budget measurable.
- Alternatives considered: Adding these cases to multi_year_invariants duplicates responsibility; running four full default scenarios wastes runtime without boundary coverage.
