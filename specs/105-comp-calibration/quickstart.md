# Quickstart: Fast Compensation Calibration Mode

How to run calibration and verify it is **fast** and **exact**. Follows the CLAUDE.md isolated-DB rule — never validate against the shared `dbt/simulation.duckdb`.

## 1. Build one full isolated baseline DB (provides the stale-but-present DC layer)

```bash
mkdir -p /tmp/cal
DATABASE_PATH=/tmp/cal/iso.duckdb \
  planalign simulate 2025-2029 --database /tmp/cal/iso.duckdb
# time this — it is the ~11-min full-sim baseline
```

## 2. Run calibration against it and time it

```bash
time planalign calibrate 2025-2029 --database /tmp/cal/iso.duckdb --target-growth 0.035
```

**Expect**: a per-year table (avg comp, YoY growth, Δ vs target, headcount, NH gap) in ~2–4 min — a clear 3–5× speedup vs. step 1 (SC-001).

## 3. Assert exactness vs. the full simulation (same config)

```bash
# Full-sim values:
duckdb /tmp/cal/iso.duckdb \
  "SELECT simulation_year, avg_compensation, yoy_growth_pct
     FROM fct_compensation_growth
    WHERE calculation_method='methodology_a_current' ORDER BY 1"

# Re-run calibrate into a separate DB copy, then compare the same columns.
```

**Expect**: avg-comp and YoY-growth columns are **identical** — bit-for-bit, because the same validated SQL produced them (SC-002 / FR-003).

## 4. Edge config — confirm it tracks the full sim, not just defaults

```bash
cp config/simulation_config.yaml /tmp/cal/edge.yaml
# edit: higher COLA + a fixed (non-default) new-hire level distribution
planalign calibrate 2025-2029 --config /tmp/cal/edge.yaml --database /tmp/cal/iso_edge.duckdb
```

Build a full sim under the same edge config and compare comp columns — must still match exactly.

## 5. Fail-fast guard

```bash
planalign calibrate 2025-2029 --database /tmp/cal/empty.duckdb   # never fully built
```

**Expect**: exits within seconds with an actionable message ("run a full simulation against this DB first"), exit code 3, **no partial build** (SC-005 / FR-011).

## 6. Studio panel

```bash
planalign studio
```

Open the **Calibration** panel, move the **target growth / COLA / merit / new-hire mix** sliders → a calibration run triggers and the per-year avg-comp + growth-vs-target charts update. Values match the CLI for the same params (SC-006).

## 7. Confirm the shared dev DB is untouched

After all default-mode runs, `dbt/simulation.duckdb` is unchanged (SC-004) — calibration only ever wrote to `/tmp/cal/*.duckdb`.
