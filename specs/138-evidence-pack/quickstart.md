# Quickstart: Cited Driver-Decomposition Evidence Packs

## Prerequisites

Run from the repository root with the existing Python 3.11 and frontend
dependencies available.

```bash
source .venv/bin/activate
```

Do not run dbt into `dbt/simulation.duckdb`. The fast tests create disposable
DuckDB files through `tmp_path`; the behavioral test runs a complete simulation
against an explicit isolated `DATABASE_PATH`.

## 1. Run the fast decomposition loop

```bash
pytest -m fast \
  tests/test_evidence_pack_service.py \
  tests/unit/cli/test_evidence_pack_command.py \
  tests/unit/test_evidence_pack_studio_contract.py -v
```

Expected outcomes:

- All six canonical metrics produce their fixed ordered driver sets.
- Named contributions plus residual equal total change exactly.
- A fully explained movement still contains residual `0`.
- Non-adjacent years behave like adjacent years.
- Zero denominators produce explicit undefined/unavailable reasons.
- Near-zero/sign-flipping changes suppress shares but retain absolute values.
- Missing source columns are unavailable, not zero.
- Repeated builder/renderer calls return identical models and Markdown bytes.

## 2. Verify every citation and the no-write boundary

```bash
pytest -m fast \
  tests/test_evidence_pack_citations.py \
  tests/test_evidence_pack_target.py \
  tests/test_evidence_pack_trust.py -v
```

Expected outcomes:

- Re-executing each cited `Q1.<result_column>` against the same fixture database
  reproduces its figure exactly.
- Citation result columns contain aggregates only.
- Serialized packs and Markdown contain no fixture employee ID, SSN, or
  absolute workstation path.
- Database size, modification timestamp, tables, and row counts are unchanged.
- A conflicting database lock returns immediately as a conflict; it is not
  retried or waited on.

## 3. Validate API and CLI parity

```bash
pytest tests/api/test_evidence_pack_api.py \
  tests/unit/cli/test_evidence_pack_command.py -v
```

Expected outcomes:

- The API requires authentication and maps not-found, unsupported, and conflict
  conditions to the documented status codes.
- `X-PlanAlign-Result-Run-Id` identifies the bound selected result.
- API `text_export`, CLI stdout, and CLI file output are byte-identical.
- Unsupported metric/year/schema errors state what is missing and include the
  available years where relevant.

Review the intentional OpenAPI change after implementation:

```bash
pytest tests/api/test_openapi_contract.py tests/api/test_route_auth_coverage.py -v
```

## 4. Build the Studio surface

```bash
cd planalign_studio
npm run build
cd ..
```

Expected outcome: TypeScript/Vite builds successfully. The source contract also
checks that the completed-result panel has metric/year controls, computing and
error states, prominent trust/residual warnings, collapsible SQL citations, and
an authenticated Markdown export action.

## 5. Run the isolated behavioral scenario

```bash
DATABASE_PATH=/tmp/planalign-evidence-pack-validation.duckdb \
  pytest -m integration tests/integration/test_evidence_pack.py -v
```

The integration fixture must create its own scenario/run archive and use the
explicit database path above (or a pytest `tmp_path` child). It must never copy
or mutate `dbt/simulation.duckdb`.

Expected outcomes:

1. A full multi-year run publishes a completed selected result.
2. Studio/API-style and CLI-style resolution bind the same run ID.
3. At least employer match cost, participation rate, and average deferral rate
   are checked across a non-adjacent span.
4. Pack figures reconcile and independently cited SQL reproduces every scalar.
5. The source result remains unchanged after all reads.

## 6. Manually produce a pack from a completed scenario

Given a completed Studio scenario directory:

```bash
SCENARIO_PATH=workspaces/<workspace>/scenarios/<scenario>

planalign evidence-pack "$SCENARIO_PATH" \
  --metric employer_match_cost \
  --base-year 2025 \
  --target-year 2027 \
  --output /tmp/employer-match-evidence.md
```

Open `/tmp/employer-match-evidence.md` in a plain text editor. Confirm it names
the scenario/run, timestamp, seed, full configuration fingerprint, base/target
values, ordered drivers, populations, explicit residual, warnings, and the Q1
SQL/result-column mapping.

To verify a figure, copy Q1 from the file and run it against the cited
run-relative `simulation.duckdb`. The named output column must equal the
canonical decimal shown in the pack. Do not execute the citation against a
different scenario or the shared development database.

## 7. Verify the interactive budget

```bash
pytest -m performance tests/performance/test_evidence_pack_performance.py -v
```

Expected outcome: pack generation for every canonical metric over a fixture of
at least 60,000 employee-years meets p95 <= 2 seconds, reads only the two
requested years, and does not sample. A frontend request shows “Computing
evidence pack…” while in flight regardless of measured duration.

## Acceptance checklist

- [x] Six inherited metric definitions match `planalign_ensemble` exactly.
- [x] Every named driver has contribution, share or suppression reason,
      population, and citation.
- [x] Residual is always present and never redistributed.
- [x] Material/dominant residual and run-trust conditions are prominent.
- [x] Studio and CLI share figures and canonical Markdown bytes.
- [x] Exports contain aggregate figures/structural metadata only.
- [x] All behavioral validation uses an isolated database.

## 8. Run feature quality gates

```bash
ruff check planalign_evidence planalign_api/models/evidence_pack.py \
  planalign_api/services/evidence_pack_service.py \
  planalign_api/services/run_trust.py planalign_api/routers/evidence_pack.py \
  planalign_cli/commands/evidence_pack.py

mypy planalign_evidence planalign_api/models/evidence_pack.py \
  planalign_api/services/evidence_pack_service.py \
  planalign_api/services/run_trust.py planalign_api/routers/evidence_pack.py \
  planalign_cli/commands/evidence_pack.py --ignore-missing-imports
```

Expected outcome: Ruff reports no violations and mypy reports no issues in the
feature modules (informational notes from pre-existing untyped modules are
acceptable).
