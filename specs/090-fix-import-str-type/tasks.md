# Tasks: Fix Import File 422 — Data Type "str" Not Recognized

**Input**: Design documents from `/specs/090-fix-import-str-type/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | quickstart.md ✅

**Tests**: TDD approach required by Constitution III — regression tests written red-first before the fix.

**Organization**: Tasks grouped by user story. US1 (upload) already works; US2 (generate parquet) is the failing path. Both are P1 and share the same one-function fix.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup (Verify Working Environment)

**Purpose**: Confirm test infrastructure is ready before writing any new tests.

- [x] T001 Verify `.venv` is active and `pytest -m fast` runs cleanly with zero failures (`pytest -m fast -q`)

**Checkpoint**: Fast test suite passes — safe to add new failing tests.

---

## Phase 2: Foundational — Red Tests (Write Before Fix)

**Purpose**: Establish the failing regression tests that will drive the fix. Per Constitution III, tests MUST be written and confirmed failing before any production code changes.

**⚠️ CRITICAL**: Run these tests and confirm they fail (ImportError or AssertionError) before moving to Phase 3.

- [x] T002 Create `tests/test_import_dtype_bug.py` with three `@pytest.mark.fast` tests:
  - `test_normalize_dtypes_removes_string_dtype` — asserts helper converts `StringDtype` → `object`
  - `test_normalize_dtypes_noop_for_object_dtype` — asserts no-op and same-object return when no `StringDtype` present
  - `test_duckdb_register_after_read_parquet` — end-to-end reproduction: CSV → source.parquet → read_parquet → normalize → register → COPY TO output.parquet (must not raise)
  - All three tests import `_normalize_dtypes_for_duckdb` from `planalign_api.services.import_service`
  - Use `tmp_path` pytest fixture for parquet file paths (no hardcoded `/tmp` paths)

- [x] T003 Run `pytest tests/test_import_dtype_bug.py -v` and confirm all 3 tests fail with `ImportError` (helper not yet defined)

**Checkpoint**: 3 red tests confirmed — ready to implement the fix.

---

## Phase 3: User Story 2 — Generate Parquet Fix (Priority: P1) 🎯 MVP

**Goal**: `generate_parquet()` succeeds for any census CSV/XLSX with string columns, eliminating the HTTP 422 "Data type 'str' not recognized" error.

**Independent Test**: `pytest tests/test_import_dtype_bug.py -v -m fast` — all 3 tests pass; no regressions in `pytest -m fast`.

### Implementation for User Story 2

- [x] T004 [US2] Add `_normalize_dtypes_for_duckdb()` private helper to `planalign_api/services/import_service.py` near the existing `_infer_output_type()` function (around line 476):
  ```python
  def _normalize_dtypes_for_duckdb(df: pd.DataFrame) -> pd.DataFrame:
      str_cols = [c for c in df.columns if isinstance(df[c].dtype, pd.StringDtype)]
      return df.astype({c: object for c in str_cols}) if str_cols else df
  ```

- [x] T005 [US2] In `generate_parquet()` in `planalign_api/services/import_service.py`, add call site 1 immediately after the `read_parquet` line (~line 251) — normalize before MappingEngine processes the DataFrame:
  ```python
  df = conn.execute(f"SELECT * FROM read_parquet('{source_path}')").df()
  conn.close()
  df = _normalize_dtypes_for_duckdb(df)   # normalize StringDtype → object
  ```

- [x] T006 [US2] In `generate_parquet()` in `planalign_api/services/import_service.py`, add call site 2 immediately before `conn.register("_transformed", transformed)` (~line 277) as a belt-and-suspenders guard:
  ```python
  transformed = _normalize_dtypes_for_duckdb(transformed)
  conn = duckdb.connect(":memory:")
  conn.register("_transformed", transformed)
  ```

- [x] T007 [US2] Run `pytest tests/test_import_dtype_bug.py -v -m fast` — confirm all 3 tests now pass (green).

**Checkpoint**: US2 fixed. Generate parquet succeeds end-to-end. T004–T007 complete.

---

## Phase 4: User Story 1 — Upload Regression Verification (Priority: P1)

**Goal**: Confirm the upload path (which already works) is not regressed by the fix. Verify the complete workflow — upload → map → generate — succeeds as one flow.

**Independent Test**: `pytest -m fast -q` — zero failures, zero regressions in existing import tests.

### Implementation for User Story 1

- [x] T008 [P] [US1] Run `pytest -m fast -q` — confirm full fast suite still passes with zero failures after the Phase 3 changes.

- [x] T009 [P] [US1] Run `pytest tests/ -k "import" -v` — confirm all existing import-related tests still pass.

**Checkpoint**: US1 upload path verified unaffected. Both P1 stories are green.

---

## Phase 5: User Story 3 — Informative Error Messages (Priority: P2)

**Goal**: When a genuine conversion error occurs (not the StringDtype bug), the 422 response body contains a user-readable message identifying the specific column and problem — not a raw Python traceback.

**Independent Test**: Trigger a genuine error (e.g., malformed mapping) via the generate endpoint; confirm the response `detail` field is a plain-language description, not an internal exception string.

### Implementation for User Story 3

- [x] T010 [US3] Review the `except Exception as exc: raise HTTPException(status_code=422, detail=str(exc))` handler in `planalign_api/routers/imports.py` (line ~521) — confirm `str(exc)` for the now-fixed `NotImplementedException` would have exposed a raw internal error string. No code change needed here since the bug is fixed, but document the finding inline as a one-line comment:
  ```python
  # detail=str(exc) exposes internal errors — future: map exceptions to user-facing messages
  ```

- [x] T011 [US3] Verify that after the fix, a successful generate returns HTTP 202 with a clean `GenerateResponse` body — no error detail visible to the caller.

**Checkpoint**: US3 verified. Internal errors no longer surface to users for this bug path.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final quality pass before the fix is considered ship-ready.

- [x] T012 [P] Run the complete fast suite one final time and confirm count matches or exceeds pre-fix count: `pytest -m fast -v --tb=short`

- [x] T013 [P] Confirm `_normalize_dtypes_for_duckdb` has no return-type annotation gap — add `-> pd.DataFrame` type hint if missing (SonarQube: return type hints must match all code paths per CLAUDE.md §9)

- [ ] T014 Run quickstart.md manual smoke test: `planalign studio`, upload a CSV with text columns, complete mapping, generate — confirm parquet file appears in the workspace without a 422 error.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Red Tests)**: Depends on Phase 1 — establishes the failing test baseline
- **Phase 3 (US2 Fix)**: Depends on Phase 2 (red tests confirmed) — this is the production code change
- **Phase 4 (US1 Verify)**: Depends on Phase 3 — regression check runs after the fix
- **Phase 5 (US3)**: Depends on Phase 3 — error message review after the fix is in place
- **Phase 6 (Polish)**: Depends on Phases 3–5 — final gate before ship

### User Story Dependencies

- **US2 (P1 — generate parquet)**: Core fix — blocks Phase 4 and 5
- **US1 (P1 — upload)**: Regression check — can run in parallel with Phase 5 once Phase 3 is done
- **US3 (P2 — error messages)**: Independent review — no code change expected; runs after Phase 3

### Within Each Phase

- T002 → T003 (must confirm red before writing production code)
- T004 → T005 → T006 → T007 (sequential: helper first, then call sites, then green check)
- T008 and T009 are independent [P] — can run in parallel
- T012 and T013 are independent [P] — can run in parallel

### Parallel Opportunities

- After T007 (Phase 3 complete): T008 + T009 (US1) can run in parallel with T010 + T011 (US3)
- After all phases: T012 + T013 (Polish) can run in parallel

---

## Parallel Example: US1 + US3 Verification (after Phase 3 complete)

```bash
# These can run at the same time (different concerns, no file conflicts):
Task T008: "pytest -m fast -q"
Task T009: "pytest tests/ -k import -v"
Task T010: "Review HTTPException handler in planalign_api/routers/imports.py"
Task T011: "Verify generate returns HTTP 202 after fix"
```

---

## Implementation Strategy

### MVP (US1 + US2 — ship the fix)

1. Complete Phase 1: Verify environment
2. Complete Phase 2: Write red tests (T002, T003)
3. Complete Phase 3: Add helper + call sites (T004–T007) → all tests green
4. Complete Phase 4: Confirm no regressions (T008, T009)
5. **STOP and VALIDATE** — import workflow succeeds end-to-end
6. Ship the fix

### Full Delivery (adds US3 + polish)

1. MVP above
2. Phase 5: Error message review (T010, T011)
3. Phase 6: Polish pass (T012–T014)

---

## Notes

- [P] tasks = different files or independent concerns, no blocking dependencies
- [Story] label maps each task to its user story for traceability
- Total production code change: 1 new function (3 lines) + 2 call-site additions (1 line each) = **5 lines**
- Total new test code: 1 file, 3 test functions (~45 lines)
- No API contract changes, no Pydantic model changes, no dbt changes
