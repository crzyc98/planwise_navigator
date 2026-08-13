# Research: Evidence Packs — Cited Driver Decomposition

## D1: Reuse the ensemble metric registry exactly

**Decision**: Use the six identifiers and aggregate semantics in
`planalign_ensemble.models.CANONICAL_METRICS` and
`planalign_ensemble.extract` as the single source of truth. Promote the needed
metric metadata to a public registry rather than copying private SQL helpers.

The inherited definitions are:

| Metric | Canonical snapshot expression | Canonical population |
|---|---|---|
| `active_headcount` | count rows where `LOWER(employment_status) = 'active'` | all snapshot rows, filtered by active indicator |
| `total_compensation` | `SUM(prorated_annual_compensation)` | all rows |
| `employer_match_cost` | `SUM(employer_match_amount)` | all rows |
| `total_employer_plan_cost` | `SUM(total_employer_contributions)` | all rows |
| `participation_rate` | average of participating indicator | all rows |
| `avg_deferral_rate` | `AVG(current_deferral_rate)` | rows where deferral is non-null under SQL `AVG` semantics |

**Rationale**: Feature 138 inherits the headline vocabulary from feature 133.
The comparison and analytics services contain similar formulas but use
different active/enrolled filters. Reusing them would make an evidence pack
disagree with the headline it explains.

**Alternatives considered**: Reuse `AnalyticsService` or `ComparisonService`
(rejected because their denominators differ); define evidence-only metrics
(rejected because it creates a competing product vocabulary).

## D2: Resolve and bind one scenario result before calculation

**Decision**: Studio/API resolves the scenario through the existing
`DatabasePathResolver`/`current_result.json` path, validates the completed
target, and binds its concrete run ID and database for the entire response. The
CLI resolves the supplied scenario path in the same way, with the established
legacy scenario-database fallback explicitly warned. Display and export come
from one response.

**Rationale**: The specification makes the scenario the analyst entry point,
while citations and provenance require one immutable result. Resolving once
preserves both. Existing current-result validation checks metadata identity,
completed status, database presence, containment, and read-only openability.

**Alternatives considered**: Accept an arbitrary database path from Studio
(rejected as unsafe and ambiguous); re-resolve during export (rejected because
the current-result pointer could change); require run UUID as the only user
input (rejected because it conflicts with the scenario-first Studio and CLI
contract, though the resolved UUID remains part of every pack).

## D3: Use exact endpoint-and-cohort decomposition

**Decision**: Build base/target populations keyed internally by `employee_id`,
then apply fixed additive identities. Active headcount uses active-state cohort
transitions. Compensation uses entered, left, and retained changes. Match and
plan cost use entered/left cost plus a symmetric retained compensation/rate
split. Participation and average deferral use symmetric numerator/denominator
attribution with separate entering, leaving, retained-behavior, and population-
reweighting drivers.

**Rationale**: These formulas are deterministic, order-independent, support
non-adjacent years, account explicitly for churn, and reconcile by construction.
The cost rate is labeled as a realized payout rate (formula, eligibility,
participation, deferral, and mix), not falsely claimed to isolate plan design.

**Alternatives considered**: Sequential factor attribution (exact but order-
dependent); only entered/left/continuing cost (does not answer compensation vs.
payout-rate question); per-employee output (violates aggregate-only scope);
assign remainder to the largest driver (violates the explicit-residual rule).

## D4: Preserve NULL/undefined semantics

**Decision**: Probe table and column availability before binding SQL. For sum
metrics, retain non-null counts so an old result with no source observations is
unavailable rather than zero. For average deferral, denominator membership is
`current_deferral_rate IS NOT NULL`. A zero retained-compensation denominator
makes both retained cost-factor drivers undefined; their unexplained movement
remains in the residual. A zero endpoint denominator makes a ratio decomposition
unavailable.

**Rationale**: Zero is a valid metric value and must not be confused with an
unsupported schema or mathematically undefined factor. Explicit undefined
reasons satisfy the honesty requirements.

**Alternatives considered**: Blanket `COALESCE(..., 0)` (rejected because it
turns absence into a false zero); infinity/zero fallback for ratios (rejected as
misleading).

## D5: Report exact fixed-scale values, residuals, and stable shares

**Decision**: Aggregate numeric inputs as `DECIMAL(38,12)`, perform domain
arithmetic with `Decimal`, and serialize canonical decimal strings. Compute the
residual last as total change minus all defined named contributions at the same
scale; never alter a driver to close. Share is signed contribution/change and
is suppressed for endpoint sign flips or near-zero changes.

Near-zero is metric-specific: zero for integral headcount; `$0.01` or
`1e-6 * max(|base|, |target|, 1)`, whichever is larger, for currency; `1e-6`
unit-rate or the relative rule for rates. Residual caution materiality is
`max(display quantum, 1% * |total change|)`. A nonzero residual whose magnitude
is at least every named contribution triggers the stronger “drivers do not
explain this movement” warning.

**Rationale**: One numeric representation makes reconciliation and cross-
surface equality deterministic. Suppression prevents enormous or meaningless
percentage shares without hiding the absolute change.

**Alternatives considered**: Binary floats rounded only in Studio (rejected due
to cross-surface drift); silently snap small residuals to zero (rejected because
the residual is an integrity signal); always show percentage shares (rejected
for sign-flip/near-zero cases).

## D6: Cite one deterministic aggregate query by result column

**Decision**: Generate one allowlisted, fully literalized SQL statement per
pack. It reads only the two requested years, may join employee IDs internally,
and returns one aggregate row containing endpoints, drivers, populations,
shares, and residual. Each figure cites `{result_store, query, result_column}`;
the text format may deduplicate the SQL as `Q1` while retaining each
`Q1.<column>` reference.

**Rationale**: Re-executing the exact SQL reproduces every figure, while one
query prevents citation formulas from drifting apart. A run-relative result-
store locator identifies the source without exposing a workstation username.

**Alternatives considered**: One raw-data query per driver (rejected because it
can expose employee rows); prose-only formula citations (not re-executable);
query digest without SQL (insufficient for independent reproduction).

## D7: Combine current-result, run metadata, and archive trust evidence

**Decision**: Use the resolved run row in append-only `run_metadata` for the
full configuration fingerprint, seed, timestamp, and year range. Reuse archived
provenance-report findings for incomplete/integrity warnings when present, and
extract the existing drift/mixed-generation logic into a shared read helper.
Verify requested years and required snapshot columns directly before analysis.

**Rationale**: Current-result publication proves a completed, readable target
but does not itself prove every intended year/table is complete. Combining the
existing evidence sources surfaces mixed generation, incomplete capture, and
missing partitions without weakening current-result invariants.

**Alternatives considered**: Trust `scenario.status` alone (insufficient);
silently use the latest `run_metadata` row rather than the resolved run ID
(could cite a different attempt); weaken current-result validation to expose
failed runs (unsafe and out of scope).

## D8: One shared service and one server-rendered Markdown export

**Decision**: Put typed models, SQL construction, decomposition, and rendering
in `planalign_evidence`. API and CLI resolve targets and call the same builder.
The API returns both the structured pack and canonical Markdown; Studio saves
that text through the authenticated API client as a Blob. CLI prints or
atomically writes exactly the same Markdown bytes.

**Rationale**: Shared calculation and rendering are necessary for byte-
identical figures and a self-contained export. Markdown is readable in a plain
text editor and pasteable into email, decks, and general-purpose assistants.

**Alternatives considered**: Frontend/CLI-specific rendering (parity risk);
JSON-only export (poor human portability); ZIP (unnecessary for one text
artifact); model-generated narrative (explicitly out of scope).

## D9: Read-only, bounded, synchronous execution

**Decision**: Use one short-lived context-managed
`duckdb.connect(..., read_only=True)`, filter to two years, return aggregate
scalars, and never create temp/persistent tables, attach databases, copy data,
cache in the result, or sample. Map incompatible locks to an immediate conflict.
Measure p95 <= 2 seconds at 60,000 employee-years; Studio shows a computing
state while the request runs.

**Rationale**: The workload is bounded and aligns with the repository’s
interactive query budget. FastAPI synchronous routes already execute without
blocking the event loop, so a job subsystem is unnecessary unless measurement
shows otherwise.

**Alternatives considered**: Persisted evidence tables/caches (violates
read-only scope); sampling (breaks exactness); asynchronous polling workflow
(premature complexity).
