# Canonical-construction documentation audit

The supported programmatic seam is:

```python
build_orchestrator(ConstructionSpec(...))
```

`OrchestratorWrapper.create_orchestrator` remains only as the CLI adapter and
delegates immediately to that seam. Studio launches the CLI with an allowlisted
origin marker; batch, invariants, parity tests, and performance tools call the
same builder. The former `factory.py`, `OrchestratorBuilder`, and direct
`PipelineOrchestrator(...)` construction sites have been removed.

`optimization.execution_engine` accepts only `dbt`. References to the compiled
engine in performance documents are explicitly historical NO-GO evidence, not
an advertised or reachable option.

Repository audits used:

```text
rg 'PipelineOrchestrator\(' --glob '*.py' (excluding construction/builder.py)
=> zero product/test construction matches

rg 'OrchestratorBuilder|planalign_orchestrator\.factory' --glob '*.py'
=> zero matches

rg 'optimization\.execution_engine' planalign_orchestrator docs README.md CLAUDE.md
=> typed dbt-only validation and documentation only
```
