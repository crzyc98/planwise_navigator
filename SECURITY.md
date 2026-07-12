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

- **Loopback binding by default** — the API binds to `127.0.0.1:8000`. Non-loopback binding is an explicit opt-in via `PLANALIGN_API_HOST`.
- **Shared-token authentication** — set `PLANALIGN_API_TOKEN` to require a token on API routes (`Authorization: Bearer <token>` or `X-API-Token`). Token comparison is constant-time. When the API is bound to a non-loopback host without a token, a security warning is logged and all routes are unauthenticated — do not run this configuration outside a trusted network segment.
- **CORS validation** — wildcard CORS (`*`) combined with a non-loopback bind is rejected at startup. Configure explicit origins via `PLANALIGN_API_CORS_ORIGINS` (default: the local Studio dev server on port 5173).
- **Scoped storage resolution** — API requests resolve databases to scenario/workspace storage; the legacy project-database fallback is disabled unless the development-only `PLANALIGN_API_ALLOW_PROJECT_DB_FALLBACK` flag is set. Artifact download routes validate paths against traversal.

WebSocket telemetry endpoints (`/ws/simulation/{run_id}`, `/ws/batch/{batch_id}`) are covered by the same shared-token boundary: when `PLANALIGN_API_TOKEN` is set, connections must supply the token as a `?token=<token>` query parameter or they are closed with policy-violation code 1008. The Studio frontend sends this automatically when built with `VITE_PLANALIGN_API_TOKEN` — a token-protected deployment must set both variables (backend env at runtime, frontend env at build time) or telemetry will not connect. Note that query parameters may appear in reverse-proxy access logs; scrub or restrict access to those logs in token-protected deployments.

### Hardening checklist for non-local deployments

1. Set a strong `PLANALIGN_API_TOKEN`.
2. Set explicit `PLANALIGN_API_CORS_ORIGINS` (never `*`).
3. Terminate TLS in front of the API (reverse proxy such as nginx/Caddy); the API itself serves plain HTTP.
4. Restrict the API and frontend ports with a host firewall to known client addresses.
5. Leave `PLANALIGN_API_ALLOW_PROJECT_DB_FALLBACK` unset in production.
6. Run the service under a dedicated low-privilege account (systemd/supervisor).

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
