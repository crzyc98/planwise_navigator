# Text Export Contract: Evidence Pack Markdown

The export is deterministic UTF-8 Markdown with LF newlines and one trailing
newline. It is complete without PlanAlign access and contains no generated-at
timestamp, absolute path, or volatile UI state.

## Required order

```text
# Evidence Pack: <Metric label>, <base year> to <target year>

## Provenance
Scenario, run ID, run timestamp, random seed, full configuration fingerprint,
run-relative result store, verification disposition.

## Warnings
Every warning in fixed severity/code order, or "None".

## Movement
Base value, target value, total change, and any share-suppression reason.

## Driver decomposition
Ordered Markdown table:
Driver | Contribution | Share of change | Population | Citation

## Residual
Residual amount and share, including zero; material/dominance caution text.

## Population treatment
Canonical population definition and entering/leaving/retained treatment.

## Citations
Result store followed by the exact Q1 SQL fenced as `sql`, then a mapping from
each displayed figure to `Q1.<result_column>`.
```

## Figure rendering

- Canonical decimal values are retained in or beside human formatting so a
  reader can reproduce the exact scalar. Currency may be shown with a `$`
  label, but it must not discard the canonical decimal string.
- Undefined values render `Undefined — <reason>`.
- Suppressed shares render `Suppressed — <reason>`.
- Negative and offsetting contributions retain their signs.
- Population text states a count and cohort meaning; it never lists members.
- Residual is always shown, including `0`.

## Citation rendering

Each displayed base value, target value, total change, driver contribution,
driver share, population count, and residual references a unique
`Q1.<result_column>`. Re-running Q1 against the named result store returns one
aggregate row whose named column exactly equals the canonical figure.

The query is emitted once to keep the text readable, but deduplication does not
weaken per-figure citation: every mapping retains the query ID and exact result
column. The query must be directly executable DuckDB SQL with integer year
literals and no parameters.

## Warning language

- A material residual uses “Caution: a material portion of the movement is
  unexplained.”
- A dominant residual additionally uses “The named drivers do not explain this
  movement.”
- Mixed-generation, incomplete-build, configuration mismatch, and integrity
  findings appear before the movement section, not as footnotes.
- A concurrent active attempt states that the pack describes the identified
  previously completed result, not the in-progress attempt.

## Determinism

Ordering is fixed by metric driver registry, warning severity/code, and figure
mapping order. The renderer must not include locale-dependent number formats,
wall-clock time, random IDs, or unordered dictionary/set iteration. The API
`text_export`, Studio download, CLI stdout, and CLI file output are the same
bytes for the same pack.
