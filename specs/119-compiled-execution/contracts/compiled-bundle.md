# Contract: Run Workspace and Immutable Compiled Bundle

## Layout

```text
var/compiled_execution/<run_id>/
├── profile/
│   └── profiles.yml
├── staging/
│   └── <invocation-uuid>/        # mutable dbt compile target
├── delegations/
│   └── <sequence>-<uuid>/        # mutable dbt run/build/seed target
├── logs/
│   └── <sequence>-<uuid>/
└── bundles/
    └── <render-context-sha256>/  # published, never a dbt target
        ├── bundle.json
        ├── manifest.json
        └── compiled/
```

Paths may be rooted in an existing run archive, but their separation and semantics do not change.

## Publication protocol

1. Create a unique staging directory on the same filesystem as `bundles/`.
2. Run dbt compile with the explicit run profile and staging `--target-path`.
3. Validate manifest version, exact selected nodes/order, supported metadata, and compiled SQL presence.
4. Compute the render-context digest and every file/content digest.
5. Write `bundle.json` last within staging.
6. Atomically rename staging to `bundles/<context-digest>`.
7. If the destination already exists, verify its complete digest before reuse; mismatches fail closed.
8. Never invoke dbt with the published directory as a target and never modify a published file.

Read-only permissions are optional defense in depth; path separation, atomic publication, and digest verification are mandatory.

## `bundle.json` minimum fields

```json
{
  "schema_version": 1,
  "context_digest": "sha256",
  "bundle_digest": "sha256",
  "project_digest": "sha256",
  "manifest_digest": "sha256",
  "dbt_version": "1.8.8",
  "adapter_version": "1.8.1",
  "database_path_digest": "sha256",
  "vars_digest": "sha256",
  "relation_state_digest": "sha256",
  "selected_unique_ids": ["model.planwise_navigator.example"],
  "nodes": [
    {
      "unique_id": "model.planwise_navigator.example",
      "sql_path": "compiled/planwise_navigator/models/example.sql",
      "sql_digest": "sha256"
    }
  ]
}
```

Raw secrets, census data, and unrestricted configuration payloads must not be copied into bundle metadata.

## Cache rules

- Cache scope is run-local for #470.
- Context equality is byte-for-byte canonical identity, not a partial-key match.
- A database commit advances relation state; reuse requires a freshly observed matching relation-state digest.
- Bundle corruption or missing content is a hard failure, never a reason to execute stale SQL or silently delegate.
- Fallback, build, seed, and test operations use fresh paths under `delegations/` and cannot alter bundle content.
