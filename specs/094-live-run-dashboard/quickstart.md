# Quickstart: Live Simulation Run Dashboard

**Feature**: 094-live-run-dashboard

## Prerequisites

```bash
source .venv/bin/activate
uv pip install -e ".[dev]"          # if deps changed
cd planalign_studio && npm install  # if frontend deps changed
```

## Run the fast tests

```bash
pytest -m fast tests/test_telemetry_emitter.py \
               tests/test_output_parser_structured.py \
               tests/test_telemetry_state.py \
               tests/test_run_telemetry_endpoint.py
```

## Manual verification (maps to spec user stories)

Launch Studio and start a multi-year run:

```bash
planalign studio --verbose
# Open a workspace with a census → Simulation Control → select scenario → Start Simulation
```

**US1 — Live stats (P1)**: While running, the stats panel shows per-event-type counts and "Year N of M". Counts jump at each year boundary (≤5s after the year's event generation completes). After completion, verify counts match the database:

```bash
duckdb workspaces/<ws>/scenarios/<sc>/simulation.duckdb \
  "SELECT event_type, COUNT(*) FROM fct_yearly_events GROUP BY 1 ORDER BY 1"
```

**US2 — Activity feed (P2)**: The right panel shows timestamped milestones (stage transitions, "Year 2025 complete — … (48.2s)"), not per-employee rows. Trigger a failure (e.g., temporarily point the scenario at a missing census) and confirm a red error milestone + failed terminal state.

**US3 — Trend chart (P3)**: The placeholder box is gone; a live events/sec + memory chart accumulates points for the whole run and stays readable on a 10+ minute run.

**US4 — Reliable telemetry (P1)**:

1. *Refresh restore*: mid-run, hard-refresh the browser → progress, counts, and full milestone history reappear within ~3s.
2. *Reconnect/backoff*: in DevTools → Network, set "Offline" for ~20s mid-run, then back online → badge goes live again ≤10s and state resyncs (no frozen stale values). Console shows backoff intervals growing (2s, 4s, 8s…).
3. *Polling fallback*: stay offline past 5 reconnect attempts → badge shows degraded/polling; restore network → REST polling resumes updates, then WS upgrade returns the badge to live.
4. *Terminal delivery*: go offline just before the run finishes; come back after it completes → UI shows COMPLETED (never stuck on "running"). Same check for Stop (cancelled) and a failing run.

**Idle state**: with no run active, the screen shows last-run summary / start prompt — no placeholders.

## Structured telemetry spot-check

```bash
# Sentinel lines should appear in the run's log
grep "PLANALIGN_TELEMETRY|" workspaces/<ws>/scenarios/<sc>/runs/<run_id>/simulation.log | head
```

## REST snapshot spot-check

```bash
curl -s localhost:8000/api/scenarios/<scenario_id>/run/telemetry | python -m json.tool | head -40
```
