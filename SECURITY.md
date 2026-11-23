# Security Policy

PlanAlign Engine is an **on-premises** workforce and DC-plan simulation platform. It processes employee census data (PII and compensation data) and is designed to run entirely inside a controlled network with **zero cloud dependencies**.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 3.6.x   | ✅ Active |
| 3.5.x   | ⚠️ Critical fixes only |
| 3.4.x   | ⚠️ Critical fixes only |
| 3.3.x   | ⚠️ Critical fixes only |
| 3.2.x   | ⚠️ Critical fixes only |
| 3.1.x   | ⚠️ Critical fixes only |
| 3.0.x   | ⚠️ Critical fixes only |
| 2.2.x   | ⚠️ Critical fixes only |
| 2.1.x   | ⚠️ Critical fixes only |
| < 2.1   | ❌ Unsupported |

## Reporting a Vulnerability

Do **not** open a public GitHub issue for security vulnerabilities.

- Report privately via **GitHub Security Advisories** ("Report a vulnerability" on the repository's Security tab), or contact the repository owner directly.
- Include: affected component (CLI / API / Studio / dbt models), reproduction steps, impact assessment, and the version or commit SHA.
- You should receive an acknowledgment within 5 business days. Please allow a reasonable disclosure window before sharing details publicly.

## Deployment Security Model

### Network defaults (PlanAlign API / Studio)

The FastAPI backend ships with safe-by-default network settings:

- **Loopback binding by default** — both the API and Studio frontend bind to loopback (`127.0.0.1`). Non-loopback binding is an explicit opt-in via `PLANALIGN_API_HOST` or `planalign studio --host`. The Vite development server accepts only an explicit Host allowlist; set `PLANALIGN_STUDIO_ALLOWED_HOSTS` to a comma-separated list when using DNS names.
- **Host header allowlist** — the API answers `400` to HTTP and WebSocket requests whose `Host` is not `localhost`, `127.0.0.1`, `::1`, or the configured bind host (when it is a specific address, not `0.0.0.0`/`::`). Set `PLANALIGN_API_ALLOWED_HOSTS` to a comma-separated list to replace the defaults, for example when serving the API under a DNS name; wildcards are not supported. Studio needs no extra setting: its Vite proxy sends the API's own address as `Host`.
- **Shared-token authentication** — set `PLANALIGN_API_TOKEN` to require authentication on API routes, including `/api/docs`, `/api/redoc`, and `/api/openapi.json`. Scripts and CLI callers pass `Authorization: Bearer <token>` or `X-API-Token`. Studio signs in on first load via `POST /api/auth/session`, which verifies the token in constant time and issues an `HttpOnly`, `SameSite=Strict`, `Path=/` session cookie (`planalign_session`, marked `Secure` on HTTPS requests, with TTL controlled by `PLANALIGN_API_SESSION_TTL_HOURS`, default 12 hours). State-changing cookie-authenticated requests and `POST`/`DELETE /api/auth/session` also require an `Origin` allowed by `PLANALIGN_API_CORS_ORIGINS`. `VITE_`-prefixed environment variables are compiled into the public frontend bundle and must never hold tokens or other secrets. When set, `PLANALIGN_API_TOKEN` must be at least 16 non-whitespace characters; empty, whitespace-only, or shorter values fail startup validation (leave it unset to disable token authentication on loopback). Token comparison is constant-time and rejects empty supplied tokens. When the API is bound to a non-loopback host without a token, a security warning is logged and all routes are unauthenticated — do not run this configuration outside a trusted network segment.
- **CORS validation** — wildcard CORS (`*`) combined with a non-loopback bind is rejected at startup. Configure explicit origins via `PLANALIGN_API_CORS_ORIGINS` (default: the local Studio dev server on port 5173). `planalign studio` sets it to the addresses it serves Studio from unless the variable is already set.
- **Scoped storage resolution** — API requests resolve databases to scenario/workspace storage; the legacy project-database fallback is disabled unless the development-only `PLANALIGN_API_ALLOW_PROJECT_DB_FALLBACK` flag is set. Artifact download routes validate paths against traversal.

WebSocket telemetry endpoints (`/ws/simulation/{run_id}`, `/ws/batch/{batch_id}`) require an `Origin` allowed by `PLANALIGN_API_CORS_ORIGINS`; missing or disallowed Origins are closed with policy-violation code 1008. When `PLANALIGN_API_TOKEN` is set, WebSocket handshakes authenticate with the `planalign_session` cookie (sent automatically by the browser after Studio sign-in) or an `Authorization: Bearer <token>` header; unauthenticated connections are closed with code 1008. Query-string tokens are not accepted.

### Git remote trust boundary (workspace sync)

`POST /api/sync/init` and `planalign sync init` accept a Git remote URL that the server will contact. Every remote URL passes a policy gate (`planalign_api/services/remote_policy.py`) at initialization and again before every `fetch`, `pull`, and `push` against the stored `origin` URL(s), and Git always receives the normalized, validated URL:

- **URL syntax and host rules** — URLs containing `#`, `?`, `\`, `%`, whitespace, or control characters are rejected. At most one `@` is permitted in the authority, userinfo must match `^[A-Za-z0-9._-]+(:[^@/\s]*)?$`, and neither the user nor the host may start with `-`. Git-style authority parsing must agree with `urllib.parse` on the host, and numeric/hex/octal host strings are rejected unless they round-trip as canonical dotted-quad IPv4 addresses.
- **Scheme allowlist and transport restrictions** — only `https` and `ssh` (including scp-style `user@host:path`) are accepted by default. Widen only deliberately via `PLANALIGN_API_GIT_REMOTE_ALLOWED_SCHEMES` (comma-separated, e.g. `https,ssh,git`). `file://`, local filesystem paths, and `ext::`/helper transports are always rejected. Every Git network operation runs with `GIT_TERMINAL_PROMPT=0`, `http.followRedirects=false`, `protocol.allow=never`, and explicit `protocol.<scheme>.allow=always` entries for the configured network schemes, written into local `.git/config` and re-asserted via process-level Git config overrides on each operation.
- **Symlink protection and staging allowlist** — `core.symlinks=false` is set at initialization and re-asserted before every pull, and a post-pull check removes any symlinks created on disk. Sync staging only adds an explicit allowlist of workspace and scenario configuration files (`workspace.json`, `base_config.yaml`, `scenarios/*/scenario.json`, `scenarios/*/overrides.yaml`) plus `.gitignore`; symlinks, runtime/build directories (`dbt_project/`, `calibration_jobs/`, `runs/`, `checkpoints/`, `target/`), and `.planalign-sync.yaml` are never staged.
- **Host allowlist (optional)** — set `PLANALIGN_API_GIT_REMOTE_ALLOWED_HOSTS` to a comma-separated list of exact hosts or domain suffixes (e.g. `git.corp.example.com`). Empty (default) permits any public host.
- **Private-network blocking** — hostnames are resolved via DNS and *every* returned address (unwrapping IPv4-mapped IPv6 addresses) must be a globally reachable unicast address (`is_global`, excluding multicast and reserved ranges) unless `PLANALIGN_API_GIT_REMOTE_ALLOW_PRIVATE_NETWORKS=true` — enable it only for deployments that legitimately sync to an internal Git server on a trusted network. Client responses return a generic `"Remote host is not an allowed destination"` error without revealing resolved IP addresses; full details are logged server-side.
- **Credential handling and redaction** — all userinfo is removed from `scheme://` URLs in API responses (including `GET /api/sync/config` and `GET /api/sync/status`), sync log entries, server logs, and error messages (plain scp-style `git@host:path` without secrets remains readable). `.planalign-sync.yaml` stores only the credential-free URL, is excluded via `.gitignore`, and is never committed; existing sync config files containing credentials are automatically rewritten without them on load, and a `.planalign-sync.yaml` tracked by an earlier version is removed from the sync repo on the next push. A token already pushed in earlier commits stays in that remote's history: rotate it. Any authenticated remote URL resides only in `.git/config`, and `.planalign-sync.yaml`, `.planalign-sync-log.json`, and `.git/config` are written with mode `0600` on POSIX systems.
- Rejected URLs return HTTP 400 from the API and exit non-zero from the CLI, without creating the repository or contacting any host.

### Hardening checklist for non-local deployments

1. Set a strong `PLANALIGN_API_TOKEN` in the backend environment only (never in `VITE_*` frontend variables, which are public in the built bundle); Studio users sign in through the session form.
2. Set explicit `PLANALIGN_API_CORS_ORIGINS` (never `*`).
3. Terminate TLS in front of the API (reverse proxy such as nginx/Caddy) so traffic is encrypted and the `planalign_session` cookie is issued with `Secure`; the API itself serves plain HTTP.
4. Restrict the API and frontend ports with a host firewall to known client addresses.
5. Leave `PLANALIGN_API_ALLOW_PROJECT_DB_FALLBACK` unset in production.
6. Run the service under a dedicated low-privilege account (systemd/supervisor).
7. If workspace sync is exposed, restrict destinations with `PLANALIGN_API_GIT_REMOTE_ALLOWED_HOSTS` and keep `PLANALIGN_API_GIT_REMOTE_ALLOW_PRIVATE_NETWORKS` disabled unless the network is trusted.

### Calculated-field expression evaluator (data import)

Import field mappings support `calculated_field` transformations whose expressions are supplied via the mapping API and persisted in workspace `mapping.json`/template files. These expressions are **not** evaluated with Python `eval()`/`exec()`. `planalign_api/services/mapping_engine.py` parses each expression with `ast.parse(..., mode="eval")` and enforces a grammar whitelist before interpreting it directly:

- Allowed: arithmetic operators (`+`, `-`, `*`, `/`), unary plus/minus, string/int/float literals, and references to exact existing DataFrame columns.
- Rejected: function calls, attribute access, subscripts/slicing, comprehensions, lambdas, walrus assignments, f-strings, boolean/comparison/bitwise operators, unknown column names, and any other node type.
- No Python globals or builtins are exposed to expressions at any point.

Do not reintroduce dynamic evaluation (`eval`, `exec`, `compile`, pandas `.eval`/`.query`) on user- or config-supplied expressions; extend the whitelist interpreter deliberately if new operators are ever required.

## Data Handling

- **Census data is PII.** Input files under `data/`, runtime outputs under `var/`, and all `*.duckdb` databases are git-ignored — never commit them. Verify before pushing: `git status --ignored data/ var/ dbt/*.duckdb`.
- **Database isolation**: each scenario runs against its own DuckDB file; batch and Studio runs never share state across scenarios.
- **Workspace sync** (`planalign sync`) pushes workspace *configuration* to a Git remote you control. Review what a workspace contains before syncing it to a shared remote, and use a private repository.
- **Excel exports** contain employee-level projections; treat them with the same controls as the source census.
- **File-system permissions** are the primary access control for databases and exports — restrict the deployment directory accordingly.

## Audit & Traceability

Security-relevant properties of the simulation engine itself:

- **Immutable event trail**: every modeled event carries a UUID, timestamp, and provenance keys (`scenario_id`, `plan_design_id`, `simulation_year`).
- **Deterministic reproducibility**: identical inputs + seed + software version reproduce identical outputs, enabling independent verification.
- **Export metadata**: batch exports embed the git commit SHA, software version, seed, and configuration for traceability.

## Dependencies & Supply Chain

- Runtime dependencies are pinned or floored in `pyproject.toml` and mirrored in `requirements.txt`; the resolved graph is locked in `uv.lock`.
- `pyproject.toml` is the dependency declaration and holds the core runtime pins (DuckDB, dbt-core, dbt-duckdb, Pydantic); verify them against `requirements.txt` and `uv.lock` using the [release checklist](docs/VERSIONING_GUIDE.md#release-checklist). Upgrade deliberately, not opportunistically.
- The Studio frontend bundles **all** assets locally via Vite. Never add CDN `<script>`/`<link>` tags or import maps to `index.html` — this is both a security and a corporate-firewall requirement.
- Report vulnerable-dependency findings through the same private channel as code vulnerabilities.
- A `pip-audit` CI gate (`python-dependency-audit` job, `.github/workflows/ci.yml`) runs on every PR/push against `requirements.txt`, `requirements-dev.txt` and an export of `uv.lock`. It fails the build on any advisory not explicitly listed below — new findings must be remediated or added here with justification, never silently ignored in CI.

### Approved Python Dependency Exceptions

The dated upgrade records below describe validation of the versions used at
that time; they are historical evidence, not the current dependency inventory.

`pytest`/`pytest-cov`/`pytest-mock`/`pytest-xdist`/`pytest-split` and `mkdocs`/`mkdocs-material`/`pymdown-extensions` were bumped directly (2026-09-21) — no longer exceptions. Verified: full fast suite (2,776 tests) plus the `--splits`/`--group`/`--cov` flags CI's sharded job relies on all pass unchanged under pytest 9.1.1.

`dbt-core` 1.8.8 -> 1.9.11, `dbt-duckdb` 1.8.1 -> 1.9.6, and `duckdb` 1.0.0 -> 1.1.3 were bumped (#705 phase 2, 2026-09-21), which pulled `dbt-common` to 1.39.0, `deepdiff` to 8.6.2, and `protobuf` to 6.33.6 via the resolver -- clearing the four exceptions below. Verified: fast suite (2,766 tests, plus 10 pre-existing local-only tests not tracked in git) and the full `multi_year_invariants`/`edge_config_matrix` integration suite (68 tests) pass; a same-config 5-year simulation (2025-2029, seed 42) run in parallel on an isolated DB against both the old and new engine pins produced byte-identical `fct_yearly_events` and `fct_workforce_snapshot` on every business column (compensation, deferral rates, event counts, ages, tenure) -- the only differences were the expected non-deterministic `created_at`/`snapshot_created_at` timestamps and float64 last-bit noise (max abs diff 1.4e-17) in 1,079 of 93,904 rows' diagnostic `event_probability` column, not used in any decision logic. The bump also surfaced a real dbt-core 1.9 breaking change: a bare `data_tests:` key in `dbt/tests/schema.yml` (used as directory-scoped config with `+severity`/`+store_failures`/`+schema`) is only valid as a list of test definitions per dbt's own docs, not `+`-prefixed config -- dbt-core 1.8 silently tolerated it, 1.9 correctly rejects it. Consolidated into `dbt_project.yml`'s existing `data_tests:` block, the only supported location for this config.

There are currently **no active Python `pip-audit` exceptions**. The previously tracked `sqlparse` (`PYSEC-2026-3696`–`3699`, `PYSEC-2026-3923`, fixed in `0.6.0` / locked at `0.6.1`, #1191) and `black` (`PYSEC-2024-48`, `PYSEC-2026-2120`, `PYSEC-2026-2121`, fixed in `26.3.1` / pinned at `26.10.1`) entries have been resolved and removed from `.github/workflows/ci.yml`.

### Approved Studio Dependency Exceptions

Temporary `npm audit` exceptions for `planalign_studio`, listed in `planalign_studio/scripts/audit-dependencies.mjs`. Any other high or critical advisory fails CI, and so does an exception past its review date. Owner: crzyc98.

| Advisory | Package | Fix version | Review by | Exposure assessment |
|---|---|---|---|---|
| GHSA-fc5q-39xc-vjpf | picomatch <=4.0.7 | none yet | 2026-12-15 | ReDoS on crafted extglob patterns. picomatch runs only in Node build and test tooling (`vite`, `tinyglobby`, `fdir`, `vitest`) on first-party glob patterns from our own config. It isn't in the browser bundle and never sees user input. Remove the exception once a patched picomatch ships. |

## Scope

In scope: the `planalign_*` Python packages, the dbt project, the Studio frontend, and the CLI.
Out of scope: vulnerabilities requiring physical access, social engineering, or misconfiguration explicitly warned against in this document (e.g., running non-loopback without a token).
