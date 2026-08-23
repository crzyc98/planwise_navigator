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

## Scope

In scope: the `planalign_*` Python packages, the dbt project, the Studio frontend, and the CLI.
Out of scope: vulnerabilities requiring physical access, social engineering, or misconfiguration explicitly warned against in this document (e.g., running non-loopback without a token).
