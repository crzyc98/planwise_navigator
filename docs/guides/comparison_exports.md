# Cost Comparison exports

Select scenarios on Cost Comparison, then choose **Excel**, **Tableau**, or
**Parquet** to download their full workforce snapshots, census, and export metadata.

Parquet downloads a ZIP containing `workforce_snapshot.parquet`, `census.parquet`,
and `metadata.parquet`. Extract the archive to read each dataset with DuckDB,
pandas, or another Parquet reader. Decimal, date, and timestamp types are preserved,
and the export has no Excel sheet row limit.

Workforce rows include Studio `scenario_name` and `scenario_id` labels across all
simulation years. When selected scenarios use the same census path, the census is
included once; otherwise census rows include scenario labels. Metadata records
the workspace, export time, selected run IDs, and census paths.

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
