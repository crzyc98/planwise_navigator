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

The API accepts `format=parquet` at
`GET /api/workspaces/{workspace_id}/analytics/compare/export?scenarios=<ids>`
and returns `application/zip`. Source databases are opened read-only, and temporary
export files are removed after the download.

Validate with disposable synthetic databases:

```bash
source .venv/bin/activate
pytest tests/api/test_comparison_export.py tests/api/test_openapi_contract.py -q
npm --prefix planalign_studio run typecheck
npm --prefix planalign_studio run build
```
