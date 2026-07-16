# Quickstart: API Contract Tests

## Running the new tests

```bash
source .venv/bin/activate
pytest tests/api/test_openapi_contract.py tests/api/test_route_auth_coverage.py -v
# or as part of the fast suite:
pytest -m fast tests/api/
```

## Updating the OpenAPI snapshot after an intentional API change

1. Make the endpoint change (add a field, new router, changed status code, etc.).
2. Regenerate the committed snapshot:
   ```bash
   python -c "
   import json
   from planalign_api.main import create_app
   json.dump(create_app().openapi(), open('tests/api/snapshots/openapi_schema.json', 'w'), indent=2, sort_keys=True)
   "
   ```
3. Run `git diff tests/api/snapshots/openapi_schema.json` and review the diff as part of your PR — this review step is the point of the snapshot (per spec.md FR-002).
4. Re-run `pytest tests/api/test_openapi_contract.py` to confirm it now passes.

## Adding a new intentionally-public route

If a new route genuinely should not require the API token (like `/api/health`), add its `(path, method)` tuple to `PUBLIC_ROUTES` in `tests/api/test_route_auth_coverage.py` in the same PR that adds the route.

## Verifying the "no test-code change needed for new routers" guarantee

1. Add a throwaway router with one `GET` endpoint to `planalign_api/main.py` (e.g., `@app.get("/api/_scratch")`), protected the normal way (via `dependencies=protected_dependencies` or an inline `Depends(require_api_token)`).
2. Run `pytest tests/api/test_route_auth_coverage.py` with no other changes — it should now also assert 401/authorized behavior on `/api/_scratch` and pass.
3. Revert the throwaway route.
