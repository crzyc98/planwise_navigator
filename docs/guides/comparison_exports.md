# Cost Comparison exports

Select scenarios on Cost Comparison, then choose **Excel**, **Tableau**, or
**Parquet** to download their full workforce snapshots, census, and export metadata.

Parquet downloads a ZIP containing `workforce_snapshot.parquet`, `census.parquet`,
and `metadata.parquet`. Extract the archive to read each dataset with DuckDB,
pandas, or another Parquet reader. Decimal, date, and timestamp types are preserved,
and the export has no Excel sheet row limit.

Workforce rows include Studio `scenario_name` and `scenario_id` labels across all
simulation years. The census is included once only when the selected runs contain
identical census tables (schema, values, and duplicate counts). Otherwise census
rows include scenario labels, even when the runs used the same file path before
and after an upload was replaced. The comparison reads the archived database
tables; it does not reopen the current workspace census.

Metadata records the workspace, export time, selected run IDs, and census paths
from each selected run's archived configuration. Census paths are blank when that
historical configuration is unavailable; current scenario settings are not used
as a substitute.

## Effective year

Cost Comparison's **Effective year** sets the year every non-anchor scenario's
design takes effect (#791). For each year before it, those scenarios show the
anchor's figures, read from the anchor's run; from that year on they show their
own. Charts, tables, totals, cumulative views and differences from the anchor all
use the combined years. A year the supplying run did not simulate shows as
unavailable, and so does every total that needs it. The default is the first
simulation year, which leaves the page and every export exactly as before.

The exports follow the same rule. Excel, Tableau and Parquet take each non-anchor
scenario's snapshot rows before the effective year from the anchor's run,
labelled with the scenario's name. Their metadata adds `effective_year` and, per
scenario, a `supplied_by` row naming the run behind each range of years. The
summary workbook adds an **Effective year** row to its Notes sheet.

Each run still uses its own design from the first year, so this is an
approximation. Match and core formula changes are close to exact. Auto-enrollment,
deferral escalation, eligibility and vesting changes are not: the scenario's run
has built up participation and vesting history a mid-run switch wouldn't have
yet. When a scenario's archived run settings differ from the anchor's in any of
those, or can't be read, the page shows a warning, and the exports carry it as an `accuracy_note`
(metadata) or **Accuracy note** (summary workbook). A later effective year can't
yet be combined with grandfathering or net of forfeitures; the page and the API
reject the combination.

The API takes `anchor=<id>&effective_year=<year>` on
`GET .../analytics/dc-plan/compare` and `GET .../analytics/compare/export`, and
`view.effective_year` on `POST .../analytics/compare/summary-export`.

The API accepts `format=parquet` at
`GET /api/workspaces/{workspace_id}/analytics/compare/export?scenarios=<ids>`
and returns `application/zip`. Source databases are opened read-only, and temporary
export files are removed after the download.

Validate with disposable synthetic databases:

```bash
source .venv/bin/activate
pytest tests/api/test_comparison_export.py tests/api/test_cost_comparison_effective_year.py \
  tests/api/test_openapi_contract.py -q
npm --prefix planalign_studio run typecheck
npm --prefix planalign_studio run build
```
