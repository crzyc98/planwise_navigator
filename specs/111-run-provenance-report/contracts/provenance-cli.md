# CLI Contract: Run Provenance Report

## Command

```text
planalign provenance RUN_ID --output-dir DIRECTORY [--workspaces-root DIRECTORY] [--force]
```

## Inputs

| Input | Required | Contract |
|---|---|---|
| `RUN_ID` | yes | Exact archived run UUID. No `latest`, scenario fallback, or prefix matching. |
| `--output-dir` | yes | Existing or creatable destination outside the selected run archive. |
| `--workspaces-root` | no | Existing workspace root; defaults to the configured Studio workspace root. The command does not create a missing root. |
| `--force` | no | Allows replacement of the two destination report files only. It never permits archive changes. |

Options for current `--config`, `--database`, census, seed, scenario, or plan design values are intentionally absent; these could enable prohibited current-state substitution.

## Successful output

Every successful invocation writes both:

```text
<output-dir>/<run-id>-provenance.json
<output-dir>/<run-id>-provenance.md
```

Both render from one report object and contain the same evidence, missing-evidence findings, verification disposition, digest, and sign-off structure. The command prints a concise Rich summary containing:

- run ID and archived status;
- `Fully Verified`, `Incomplete`, or `Unverifiable`;
- SHA-256 report digest;
- missing required-evidence count;
- the two output paths.

`Incomplete` and `Unverifiable` are successful report-generation outcomes and return exit code 0 when archive identity is sound.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Both reports generated, including honest incomplete/unverifiable reports |
| `1` | Unexpected internal failure; no valid pair emitted |
| `2` | Invalid arguments, unsafe output destination, or existing output without `--force` |
| `3` | Exact archived run not found |
| `4` | Duplicate/conflicting run identity or archive changed during read |

The command writes the pair through temporary destination files and publishes them only after both render successfully. A partial output pair is removed on failure; no selected run archive file is opened for writing.

## Determinism

For unchanged archived evidence:

- CLI JSON `report` equals the API envelope's `report`;
- CLI Markdown equals the API envelope's `audit_sheet` after the standard final newline rule;
- digest equals the API `ETag` value without quotes;
- output path, request time, and `--force` do not affect evidence or digest.

## Security and privacy

- Never print or write employee identifiers, employee events, census rows, validation raw details, physical input paths, source diff text, usernames, or credentials.
- Error messages identify logical report fields and run IDs, not physical archive paths.
- The output directory must not resolve inside the selected run directory.
