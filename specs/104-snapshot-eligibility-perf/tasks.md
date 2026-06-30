---
description: "Task list for fct_workforce_snapshot eligibility decorrelation (issue #365)"
---

# Tasks: Optimize fct_workforce_snapshot Eligibility Branch

**Input**: Design documents from `/specs/104-snapshot-eligibility-perf/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅
**Branch**: `104-snapshot-eligibility-perf`

**Tests**: This is a dbt analytical-model change with no Python unit surface. The "test" is a baseline-vs-rewrite snapshot diff harness (quickstart.md) plus existing dbt schema tests — these ARE the red/green gate (per plan.md, Constitution III). They are included below.

**Organization**: Tasks grouped by user story. The whole change is one CTE rewrite in one file; US2 is largely satisfied as a byproduct of US1 and reduces to verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files / independent, no dependency on an incomplete task)
- **[Story]**: US1 (P1) or US2 (P2)
- Single mutated file: `dbt/models/marts/fct_workforce_snapshot.sql`. Scratch DBs/configs under `/tmp/feat104/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Workspace prep; no source changes yet.

- [X] T001 Confirm on branch `104-snapshot-eligibility-perf` and create scratch dir `/tmp/feat104/` (`git branch --show-current && mkdir -p /tmp/feat104`)
- [X] T002 Confirm venv active and DuckDB CLI available (orchestrator import OK; duckdb v1.4.4)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Capture the `main`/pre-edit baselines that the byte-identical guarantee is measured against. **MUST happen before any edit to the model** (CLAUDE.md §8 — never validate against the shared dev DB).

**⚠️ CRITICAL**: No model edit (Phase 3+) may begin until both baselines are captured.

- [X] T003 Capture default-config baseline → `/tmp/feat104/baseline.duckdb` (exit 0; per-year rows 2025=8116, 2026=8535, 2027=8815)
- [X] T004 [P] Create edge config `/tmp/feat104/edge.yaml` — `scope: all_eligible_employees`, `hire_date_cutoff: 2010-01-01`
- [X] T005 Capture edge-config baseline → `/tmp/feat104/baseline_edge.duckdb`
- [X] T006 [P] Pre-change facts captured: grain is `(employee_id, simulation_year)` (NOT scenario/plan — contract C2 corrected), 0 grain dups, schema saved to `describe_baseline.txt`. **`snapshot_created_at` (TIMESTAMP WITH TIME ZONE) is run-varying and MUST be excluded from every diff.** Pre-edit compiled eligibility CTE shows **two** `fct_yearly_events` refs (compiled L338 outer + L343 correlated inner)

**Checkpoint**: Baselines frozen — model edit can now begin.

---

## Phase 3: User Story 1 - Faster build, identical results (Priority: P1) 🎯 MVP

**Goal**: Replace the correlated subquery in the subsequent-years eligibility branch with a single-pass window form; `fct_workforce_snapshot` stays byte-identical while reading `fct_yearly_events` once instead of twice.

**Independent Test**: Re-run the same multi-year sims into fresh isolated DBs and diff against the Phase-2 baselines — zero rows differ (default + edge), stage time ≤ baseline.

### Implementation for User Story 1

- [X] T007 [US1] In `dbt/models/marts/fct_workforce_snapshot.sql`, rewrite the `events` subquery inside the `employee_eligibility` CTE's subsequent-years (`{% else %}`) branch (≈ L457–476): compute `MAX(simulation_year) OVER (PARTITION BY employee_id)` over all `event_type='eligibility'` rows with `simulation_year <= {{ simulation_year }}` in an inner CTE, then select rows where `simulation_year = latest_elig_year`, applying the `JSON_EXTRACT_STRING(event_details,'$.determination_type') = 'initial'` predicate **verbatim** (research.md R1/R2). Preserve the exact output columns, casts, and `current_eligibility_status` CASE from data-model.md
- [X] T008 [US1] Verify scope discipline: confirm the year-1 (`simulation_year == start_year`) branch, the `current_year_events` CTE, all other CTEs, and the `final_output` projection are byte-unchanged in the diff (`git diff dbt/models/marts/fct_workforce_snapshot.sql` touches only the target subquery) — FR-004
- [X] T009 [US1] Build the rewrite into fresh isolated DBs: `DATABASE_PATH=/tmp/feat104/rewrite.duckdb planalign simulate 2025-2027 --database /tmp/feat104/rewrite.duckdb 2>&1 | tee /tmp/feat104/rewrite.log` and `DATABASE_PATH=/tmp/feat104/rewrite_edge.duckdb planalign simulate 2025-2027 --config /tmp/feat104/edge.yaml --database /tmp/feat104/rewrite_edge.duckdb` (depends on T007)

### Validation for User Story 1 (the red/green gate)

- [X] T010 [US1] Zero-diff default config: run the per-year row-hash compare (quickstart.md §5) over `baseline.duckdb` vs `rewrite.duckdb` — every `hashes_match = true`, equal row counts (SC-001, contract C3)
- [X] T011 [P] [US1] Zero-diff edge config: same row-hash compare over `baseline_edge.duckdb` vs `rewrite_edge.duckdb` — all match (SC-004)
- [X] T012 [P] [US1] Eligibility-column anti-join: `EXCEPT` over `employee_eligibility_date, waiting_period_days, current_eligibility_status, employee_enrollment_date, is_enrolled_flag` returns `differing_rows = 0` (quickstart.md §5)
- [X] T013 [P] [US1] Grain/schema unchanged: `DESCRIBE` matches T006; no new duplicates on `(scenario_id, plan_design_id, employee_id, simulation_year)` (contract C1/C2)
- [X] T014 [US1] dbt schema tests green: `cd dbt && DATABASE_PATH=/tmp/feat104/rewrite.duckdb dbt test --select fct_workforce_snapshot --threads 1` (contract C4)
- [X] T015 [P] [US1] Performance evidence: rewrite `fct_workforce_snapshot` stage time ≤ baseline (compare logs); compiled subsequent-years query references `fct_yearly_events` **once** in the eligibility CTE vs two in T006 (SC-002/SC-003/SC-005, contract C5)

**Checkpoint**: US1 complete — decorrelated, byte-identical, no regression. This is the shippable MVP.

---

## Phase 4: User Story 2 - Consistent, maintainable source (Priority: P2)

**Goal**: The eligibility branch reads current-/relevant-year events from one self-contained source rather than a correlated double-ref.

**Independent Test**: A reviewer tracing the rewritten eligibility CTE sees a single self-contained event read, no correlated inner re-ref.

> **Note (research.md R3)**: US2's original "source from `current_year_events`" framing does **not** apply to the L466 read — it is cross-year by design (eligibility events ≤ current year), so it cannot use the current-year-only CTE without changing behavior. The L412 read is in the out-of-scope year-1 branch. The genuine redundant-scan elimination is delivered by the US1 window rewrite (two refs → one). US2 therefore reduces to verification + documenting the deferred item.

### Implementation / Verification for User Story 2

- [X] T016 [US2] Confirm the rewritten `events` subquery is self-contained (single inner CTE, one `fct_yearly_events` read) with no remaining correlated/duplicate reference inside the subsequent-years eligibility branch (FR-003, SC-005)
- [X] T017 [P] [US2] Add a brief inline comment in `dbt/models/marts/fct_workforce_snapshot.sql` above the rewritten subquery noting it replaces a correlated `MAX()` and preserves the (currently dead) `determination_type` predicate, linking issue #365

**Checkpoint**: US1 + US2 both satisfied; source is consistent and documented.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Suite-wide safety, deferred-finding capture, and PR hygiene.

- [X] T018 [P] Run `pytest -m fast` — green (no orchestrator/config regressions)
- [ ] T019 [P] File a follow-up GitHub issue for the deferred dead-code finding (research.md R2): the events-eligibility join is inert because no producer emits `determination_type`; decide remove-vs-activate as a business-rules call. Reference #365 and this branch
- [X] T020 Update `CHANGELOG.md` with the perf entry (decorrelated `fct_workforce_snapshot` eligibility branch; behavior-preserving) per VERSIONING_GUIDE
- [ ] T021 Open PR closing #365: summarize the decorrelation, the byte-identical evidence (T010–T013), the no-regression evidence (T015), and the deferred dead-code follow-up (T019)
- [ ] T022 [P] Clean up scratch artifacts under `/tmp/feat104/` once the PR captures the evidence

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Setup; **BLOCKS all model edits** (baselines must be captured pre-edit)
- **User Story 1 (Phase 3)**: depends on Phase 2 — the MVP
- **User Story 2 (Phase 4)**: depends on US1 (T007) — verification of the same edit
- **Polish (Phase 5)**: depends on US1 (and US2) complete

### Critical path

T001 → T003 (and T004→T005) → T007 → T009 → T010 → (T014/T015) → T021

### Within User Story 1

- T007 (edit) before T009 (build) before T010–T015 (validate)
- T008 is a review check on T007's diff
- T010 gates the rest; T011/T012/T013/T015 are independent checks ([P])

### Parallel Opportunities

- T004 and T006 run alongside T003 ([P])
- After T009: T011, T012, T013, T015 run in parallel ([P]); T010 and T014 are the sequential gates
- Phase 5: T018, T019, T022 are independent ([P])

---

## Parallel Example: User Story 1 validation

```bash
# After T009 (both rewrite DBs built), run these checks in parallel:
Task: "T011 Zero-diff edge config row-hash compare (baseline_edge vs rewrite_edge)"
Task: "T012 Eligibility-column EXCEPT anti-join → differing_rows = 0"
Task: "T013 DESCRIBE + grain duplicate check vs T006 precheck"
Task: "T015 Stage-time compare + compiled single-scan confirmation"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → Phase 2 Foundational (freeze baselines)
2. Phase 3: rewrite (T007), build (T009), validate (T010–T015)
3. **STOP and VALIDATE**: zero-diff + no regression — this is shippable on its own
4. Open PR closing #365

### Incremental

- US2 (Phase 4) is verification + a doc comment on the same edit — fold into the same PR.
- Phase 5 (fast suite, deferred-issue, changelog, cleanup) finalizes the PR.

---

## Notes

- [P] = different files / independent commands, no dependency on an incomplete task.
- The single source edit is `dbt/models/marts/fct_workforce_snapshot.sql`; everything else is validation/scratch.
- **Preserve the `determination_type='initial'` predicate verbatim** — removing it would change output and break byte-identity (research.md R2). The dead-code decision is deferred (T019).
- Never validate against `dbt/simulation.duckdb`; all runs use isolated `DATABASE_PATH` DBs (CLAUDE.md §8).
- Commit after T007 and after the validation passes; keep the diff minimal.
