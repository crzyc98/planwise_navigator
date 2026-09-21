# Security Policy

Fidelity PlanAlign Engine is an **on-premises** workforce and DC-plan simulation platform. It processes employee census data (PII and compensation data) and is designed to run entirely inside a controlled network with **zero cloud dependencies**.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.2.x   | ✅ Active |
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
- **Shared-token authentication** — set `PLANALIGN_API_TOKEN` to require a token on API routes (`Authorization: Bearer <token>` or `X-API-Token`). Token comparison is constant-time. When the API is bound to a non-loopback host without a token, a security warning is logged and all routes are unauthenticated — do not run this configuration outside a trusted network segment.
- **CORS validation** — wildcard CORS (`*`) combined with a non-loopback bind is rejected at startup. Configure explicit origins via `PLANALIGN_API_CORS_ORIGINS` (default: the local Studio dev server on port 5173).
- **Scoped storage resolution** — API requests resolve databases to scenario/workspace storage; the legacy project-database fallback is disabled unless the development-only `PLANALIGN_API_ALLOW_PROJECT_DB_FALLBACK` flag is set. Artifact download routes validate paths against traversal.

WebSocket telemetry endpoints (`/ws/simulation/{run_id}`, `/ws/batch/{batch_id}`) require an `Origin` allowed by `PLANALIGN_API_CORS_ORIGINS`; missing or disallowed Origins are closed with policy-violation code 1008. They are also covered by the shared-token boundary: when `PLANALIGN_API_TOKEN` is set, connections must supply the token as a `?token=<token>` query parameter or they are closed with code 1008. The Studio frontend sends this automatically when built with `VITE_PLANALIGN_API_TOKEN` — a token-protected deployment must set both variables (backend env at runtime, frontend env at build time) or telemetry will not connect. Note that query parameters may appear in reverse-proxy access logs; scrub or restrict access to those logs in token-protected deployments.

### Git remote trust boundary (workspace sync)

`POST /api/sync/init` and `planalign sync init` accept a Git remote URL that the server will contact. Because an API caller could otherwise point this at arbitrary HTTP(S), SSH, file, or Git-helper transports (an SSRF / outbound-network-control risk), every remote URL passes a policy gate (`planalign_api/services/remote_policy.py`) before any Git transport is created:

- **Scheme allowlist** — only `https` and `ssh` (including scp-style `user@host:path`) are accepted by default. Widen only deliberately via `PLANALIGN_API_GIT_REMOTE_ALLOWED_SCHEMES` (comma-separated, e.g. `https,ssh,git`). `file://`, local filesystem paths, and `ext::`/helper transports are always rejected.
- **Host allowlist (optional)** — set `PLANALIGN_API_GIT_REMOTE_ALLOWED_HOSTS` to a comma-separated list of exact hosts or domain suffixes (e.g. `git.corp.example.com`). Empty (default) permits any public host.
- **Private-network blocking** — hostnames are resolved via DNS and *every* returned address must be public. Loopback, RFC1918/ULA private, link-local (including the cloud metadata service `169.254.169.254`), reserved/multicast, and unspecified addresses are rejected unless `PLANALIGN_API_GIT_REMOTE_ALLOW_PRIVATE_NETWORKS=true` — enable it only for deployments that legitimately sync to an internal Git server on a trusted network.
- **Credential redaction** — passwords embedded in remote URLs (`https://user:pass@host/...`) are replaced with `***` in API responses, sync log entries, server logs, and error messages. Credentials are still persisted in the local `.planalign-sync.yaml` so later fetch/push operations can authenticate; protect workspace files with filesystem permissions as you would any secret.
- Rejected URLs return HTTP 400 from the API and exit non-zero from the CLI, without creating the repository or contacting any host.

### Hardening checklist for non-local deployments

1. Set a strong `PLANALIGN_API_TOKEN`.
2. Set explicit `PLANALIGN_API_CORS_ORIGINS` (never `*`).
3. Terminate TLS in front of the API (reverse proxy such as nginx/Caddy); the API itself serves plain HTTP.
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
- Core storage/transform versions are intentionally pinned (DuckDB 1.0.0, dbt-core 1.8.8, dbt-duckdb 1.8.1, Pydantic 2.7.4) — upgrade deliberately, not opportunistically.
- The Studio frontend bundles **all** assets locally via Vite. Never add CDN `<script>`/`<link>` tags or import maps to `index.html` — this is both a security and a corporate-firewall requirement.
- Report vulnerable-dependency findings through the same private channel as code vulnerabilities.
- A `pip-audit` CI gate (`python-dependency-audit` job, `.github/workflows/ci.yml`) runs on every PR/push against `requirements.txt` and `requirements-dev.txt`. It fails the build on any advisory not explicitly listed below — new findings must be remediated or added here with justification, never silently ignored in CI.

### Approved Python Dependency Exceptions

Temporary `pip-audit` exceptions, tracked in [#705](https://github.com/crzyc98/planwise_navigator/issues/705). All are currently blocked by the dbt-core 1.8.8 engine pin (see above) except `black`, a dev/build-only tooling bump deferred rather than blocked. Owner: crzyc98. Review by: 2026-12-01, or whenever the dbt-core 1.9.x migration (#705 phase 2) lands, whichever is first.

`pytest`/`pytest-cov`/`pytest-mock`/`pytest-xdist`/`pytest-split` and `mkdocs`/`mkdocs-material`/`pymdown-extensions` were bumped directly (2026-09-21) — no longer exceptions. Verified: full fast suite (2,776 tests) plus the `--splits`/`--group`/`--cov` flags CI's sharded job relies on all pass unchanged under pytest 9.1.1.

| Advisory | Package | Fix version | Exposure assessment |
|---|---|---|---|
| PYSEC-2024-203 | duckdb 1.0.0 | 1.1.0 | `sniff_csv` can read the filesystem even with `enable_external_access=false`. PlanAlign never sets that flag or sandboxes untrusted SQL — all SQL is first-party dbt project code against trusted local census data. Blocked: dbt-duckdb declares no upper bound on duckdb, but the engine version is intentionally pinned pending simulation-parity validation (#705 phase 2). |
| PYSEC-2026-2440 | dbt-common 1.10.0 | 1.34.2 / 1.37.3 | Path traversal in `safe_extract()`'s tarball handling, used by `dbt deps` when unpacking package tarballs. `packages.yml` in this repo names a small, first-party-controlled package set — no untrusted tarball source. Blocked: dbt-core 1.8.8 caps `dbt-common<1.11.0`; the fix versions require dbt-core 1.9.x+. |
| PYSEC-2026-327 | deepdiff 7.0.1 | 8.6.1 | Class-pollution in `Delta`'s constructor, chainable to DoS/RCE. PlanAlign code never calls DeepDiff's `Delta`/diff-apply APIs on untrusted input; it's pulled in transitively by dbt-common. Highest-severity item in this list — prioritize in phase 2. Blocked: transitively capped by dbt-common's `deepdiff<8.0` under dbt-core 1.8.8. |
| PYSEC-2026-2445 | deepdiff 7.0.1 | 8.6.2 | Memory-exhaustion DoS via `SAFE_TO_IMPORT` pickle unpickling. Not reachable — PlanAlign never deserializes DeepDiff delta pickles from untrusted sources. Blocked: same as PYSEC-2026-327. |
| PYSEC-2026-1805 | protobuf 4.25.9 | 5.29.6 / 6.33.5 | Recursion-depth bypass DoS in `json_format.ParseDict()` for nested `Any` messages. PlanAlign is on-premises with zero cloud dependencies (see Deployment Security Model above); nothing parses untrusted protobuf/JSON over a network boundary. Blocked: dbt-core 1.8.8 caps `protobuf<5`; fixed at dbt-core 1.9.11 (`protobuf<7,>=6`). |
| PYSEC-2026-3696, PYSEC-2026-3697, PYSEC-2026-3698, PYSEC-2026-3699 | sqlparse 0.5.5 | 0.6.0 | Code-gen string-breakout and formatting-filter issues in sqlparse's Python/PHP export modes and statement splitting. PlanAlign never calls those export modes; sqlparse is used internally by dbt to parse first-party SQL. Blocked: **no current dbt-core release allows sqlparse 0.6.0** — every checked line (1.8.x, 1.9.x, 1.10.x) caps `sqlparse<0.6.0`, and 1.10.x tightens further to `<0.5.5`. This is an upstream dbt limitation, not something we can resolve locally. |
| PYSEC-2026-3923 | sqlparse 0.5.5 | 0.6.0 | Quadratic-CPU DoS in `ReindentFilter` on attacker-controlled SQL near the grouping-token cap. All SQL processed here is first-party dbt project code (see the sqlparse `MAX_GROUPING_TOKENS` auto-patch in `planalign_orchestrator`), not attacker-controlled. Blocked: same upstream limitation as above. |
| PYSEC-2024-48, PYSEC-2026-2120, PYSEC-2026-2121 | black 23.9.1 | 26.3.1 | Regex/formatting DoS issues in black's own source-processing. Dev/CI tooling only. Deferred: black's fix requires jumping 23→26, and black upgrades commonly change default formatting rules, which would reformat the entire codebase as a side effect — that belongs in its own reviewed PR, not bundled into a dependency-audit gate. |

## Scope

In scope: the `planalign_*` Python packages, the dbt project, the Studio frontend, and the CLI.
Out of scope: vulnerabilities requiring physical access, social engineering, or misconfiguration explicitly warned against in this document (e.g., running non-loopback without a token).
