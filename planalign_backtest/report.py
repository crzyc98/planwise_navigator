"""Scorecard serialization and human-readable rendering."""

from __future__ import annotations

import json
from pathlib import Path

from planalign_backtest.errors import BacktestError
from planalign_backtest.models import Scorecard
from planalign_fit.pack import ParameterPack, _fingerprint

SCORECARD_DIR = "backtest"
JSON_NAME = "scorecard.json"
MARKDOWN_NAME = "scorecard.md"


def to_json(scorecard: Scorecard) -> str:
    payload = scorecard.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"


def render_markdown(scorecard: Scorecard) -> str:
    lines = [
        f"# Backtest scorecard — {scorecard.provenance.pack_id}",
        "",
        f"Fitted {scorecard.split.fit_years[0]}–{scorecard.split.fit_years[-1]} · "
        f"held out {', '.join(str(year) for year in scorecard.split.holdout_years)} · "
        f"seeds {', '.join(str(seed) for seed in scorecard.seeds)}",
        "",
    ]
    for period in (*scorecard.split.holdout_years, "cumulative"):
        lines.extend(
            [f"## {'Cumulative' if period == 'cumulative' else f'Year {period}'}", ""]
        )
        lines.extend(
            [
                "| Metric | Predicted | Actual | Absolute error | Percent error | Status |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for item in (
            comparison
            for comparison in scorecard.comparisons
            if comparison.period == period and comparison.observable
        ):
            percent = (
                "undefined"
                if item.percent_error is None
                else f"{item.percent_error:+.2%}"
            )
            lines.append(
                f"| `{item.metric}` | {item.predicted:,.4f} | {item.actual:,.4f} | "
                f"{item.absolute_error:+,.4f} | {percent} | **{item.status.upper()}** |"
            )
        lines.append("")
    unobservable = [item for item in scorecard.comparisons if not item.observable]
    if unobservable:
        lines.extend(["## Not observable", ""])
        for item in unobservable:
            lines.append(
                f"- `{item.metric}` ({item.period}): {item.unobservable_reason}"
            )
        lines.append("")
    lines.extend(["## Seed spread", ""])
    if len(scorecard.seeds) == 1:
        lines.extend(["No seed spread computed (1 seed).", ""])
    else:
        for item in scorecard.comparisons:
            if item.spread is None:
                continue
            position = (
                "actual inside"
                if item.spread.actual_within_spread
                else f"actual outside by {item.spread.distance_outside:+,.4f}"
            )
            lines.append(
                f"- `{item.metric}` ({item.period}): {item.spread.minimum:,.4f}–"
                f"{item.spread.maximum:,.4f}; {position}"
            )
        lines.append("")
    thresholds = scorecard.thresholds
    lines.extend(
        [
            f"**Verdict: {scorecard.verdict.upper()}** — {scorecard.verdict_summary}",
            "",
            "Thresholds (warn/fail): "
            f"headcount {thresholds.headcount.warn:.1%}/{thresholds.headcount.fail:.1%}; "
            f"compensation {thresholds.compensation.warn:.1%}/{thresholds.compensation.fail:.1%}; "
            f"flows {thresholds.flows.warn:.1%}/{thresholds.flows.fail:.1%}; "
            f"plan {thresholds.plan.warn:.1%}/{thresholds.plan.fail:.1%}.",
            f"Overrides: {', '.join(scorecard.overridden_thresholds) or 'none'}.",
            "",
            f"Scorecard fingerprint: `{scorecard.scorecard_fingerprint}`",
            "",
        ]
    )
    return "\n".join(lines)


def load_scorecard(pack_dir: Path | str) -> Scorecard | None:
    path = Path(pack_dir) / SCORECARD_DIR / JSON_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1.0.0":
            raise BacktestError(
                f"Unsupported backtest scorecard schema version: {payload.get('schema_version')}"
            )
        expected = payload.get("scorecard_fingerprint")
        scorecard = Scorecard.model_validate(payload)
    except BacktestError:
        raise
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise BacktestError(f"Corrupt backtest scorecard {path}: {exc}") from exc
    if expected != scorecard.scorecard_fingerprint:
        raise BacktestError(f"Scorecard fingerprint mismatch in {path}")
    return scorecard


def scorecard_is_current(scorecard: Scorecard, pack: ParameterPack) -> bool:
    current = _fingerprint(
        pack.config_fragment, pack.seed_files, pack.manifest.source_digest
    )
    return scorecard.provenance.pack_fingerprint == current


def write_scorecard(
    scorecard: Scorecard, pack_dir: Path | str, *, force: bool = False
) -> tuple[Path, Path]:
    directory = Path(pack_dir) / SCORECARD_DIR
    json_path, markdown_path = directory / JSON_NAME, directory / MARKDOWN_NAME
    if json_path.exists() and not force:
        raise BacktestError(
            f"{json_path} already exists, scored on {scorecard.provenance.backtest_date}. "
            "Pass --force to replace it."
        )
    directory.mkdir(parents=True, exist_ok=True)
    json_tmp, markdown_tmp = (
        directory / f".{JSON_NAME}.tmp",
        directory / f".{MARKDOWN_NAME}.tmp",
    )
    json_tmp.write_text(to_json(scorecard), encoding="utf-8")
    markdown_tmp.write_text(render_markdown(scorecard), encoding="utf-8")
    json_tmp.replace(json_path)
    markdown_tmp.replace(markdown_path)
    return json_path, markdown_path
