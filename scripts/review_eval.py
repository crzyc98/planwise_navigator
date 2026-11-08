"""Score the PR reviewer against PRs that introduced known bugs.

Each case is a merged PR whose bug a later fix commit repaired. The reviewer
runs on the original PR diff with the current REVIEW.md; a judge model then
decides whether any finding describes the known bug. Controls are PRs with no
follow-up fix, so findings there measure noise. Rerun after changing REVIEW.md
or the review prompt or model, and keep a change only if the score improves.

Usage: python3 scripts/review_eval.py [--prompt single|deep] [--model opus] [--only ID ...] [--jobs 4]
Results print as a table and are saved under var/review-evals/.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, TypeAdapter

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "scripts" / "review_eval_cases.json"
OUT_DIR = ROOT / "var" / "review-evals"
READ_TOOLS = "Read Grep Glob Bash(git diff:*) Bash(git log:*) Bash(git show:*)"
JUDGE_MODEL = "sonnet"
WORKTREE_LOCK = Lock()  # git worktree add/remove are not safe to run concurrently

REVIEW_PROMPT = """You are reviewing a pull request in this repository (checked out at the PR's merge commit).
PR description:
{intent}

Review `git diff {sha}^ {sha}` for correctness bugs. Read CLAUDE.md and the surrounding code, not just the diff.
Follow this review guide exactly:

{review_md}

Verify each candidate against the code before reporting it; drop anything you can't tie to a line and input.
Reply with only a JSON array, no prose: [{{"file": "...", "line": 0, "severity": "Important|Nit|Pre-existing",
"summary": "...", "scenario": "..."}}]. Reply [] if nothing needs fixing."""

DEEP_PROMPT = """You are leading a review of a pull request in this repository (checked out at the PR's merge commit).
PR description:
{intent}

The diff is `git diff {sha}^ {sha}`. This is the review guide every reviewer must follow:

{review_md}

Step 1. Launch three subagents in parallel with the Agent tool. Give each the PR description, the diff command,
the review guide above, and one lens. Each reads the diff and the code around it (callers, consumers, validators,
schemas) and returns candidate bugs with file, line, and a concrete input that breaks.
- Lens A, contracts between layers: values one layer accepts, produces or defaults vs. what the layers it talks to
  (Studio UI, API, config export, orchestrator, dbt) accept or expect. Limits, units, null/empty handling, IDs.
- Lens B, data edge cases and time: empty, missing or null rows; missing or partial years; mid-year events;
  first and last simulation year; databases or saved workspaces created before this change.
- Lens C, intent: does every code path do what the PR description claims? What did the old code do that the new
  code no longer does? For fixes, is the root cause fixed or only one symptom?

Step 2. Merge duplicates. For each candidate, re-read the code yourself and confirm the failure scenario is real.
Drop anything you can't tie to a line and input. Then tag severity using the review guide.

Reply with only a JSON array, no prose: [{{"file": "...", "line": 0, "severity": "Important|Nit|Pre-existing",
"summary": "...", "scenario": "..."}}]. Reply [] if nothing needs fixing."""

PROMPTS = {
    "single": (REVIEW_PROMPT, READ_TOOLS),
    "deep": (DEEP_PROMPT, READ_TOOLS + " Agent Task"),
}

JUDGE_PROMPT = """A code reviewer looked at a pull request. Known bugs in that PR (found later):
{bugs}

The reviewer's findings:
{findings}

For each known bug, say which finding (by index) describes the same defect, or null if none does.
A finding matches only if acting on it would have fixed or exposed that bug.
Reply with only JSON: {{"matches": [{{"bug": 0, "finding": 2}}, ...]}}"""


class Finding(BaseModel):
    file: str = ""
    line: int = 0
    severity: str = ""
    summary: str = ""
    scenario: str = ""


class Match(BaseModel):
    bug: int
    finding: int | None = None


class JudgeReply(BaseModel):
    matches: list[Match] = []


class Bug(BaseModel):
    fix: str
    description: str


class Item(BaseModel):
    """A case (intro + known bugs) or a clean control (sha only)."""

    id: str
    intro: str | None = None
    sha: str | None = None
    bugs: list[Bug] = []

    @property
    def commit(self) -> str:
        return self.intro or self.sha or ""


class Result(BaseModel):
    id: str
    sha: str
    findings: list[Finding] = []
    bugs: list[str] = []
    caught: list[str] = []  # "important" | "other" | "missed"
    seconds: float = 0.0
    error: str = ""


FINDINGS = TypeAdapter(list[Finding])


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def claude(prompt: str, model: str, cwd: Path, tools: str | None = None) -> str:
    """Run one non-interactive Claude Code call and return its final text."""
    args = ["claude", "-p", prompt, "--model", model, "--output-format", "json"]
    if tools:
        args += ["--allowedTools", tools]
    out = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True, timeout=1800
    )
    return str(json.loads(out.stdout)["result"])


def extract_json(text: str) -> str:
    """Return the JSON array or object in a model reply, without fences or prose."""
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    body = match.group(1) if match else text
    start = min(i for i in (body.find("["), body.find("{")) if i >= 0)
    return body[start : max(body.rfind("]"), body.rfind("}")) + 1]


def review(sha: str, model: str, variant: str) -> list[Finding]:
    """Review one commit's diff in a throwaway worktree."""
    review_md = (ROOT / "REVIEW.md").read_text(encoding="utf-8")
    intent = git("log", "-1", "--format=%B", sha).strip()
    with tempfile.TemporaryDirectory(prefix="review-eval-") as tmp:
        tree = Path(tmp) / "tree"
        with WORKTREE_LOCK:
            git("worktree", "add", "--detach", "-q", str(tree), sha)
        try:
            template, tools = PROMPTS[variant]
            prompt = template.format(intent=intent, sha=sha, review_md=review_md)
            raw = extract_json(claude(prompt, model, tree, tools))
        finally:
            with WORKTREE_LOCK:
                git("worktree", "remove", "--force", str(tree))
    return FINDINGS.validate_json(raw)


def judge(bugs: list[str], findings: list[Finding]) -> list[str]:
    """Label each known bug as caught by an Important finding, another finding, or missed."""
    if not findings:
        return ["missed"] * len(bugs)
    listed = "\n".join(
        f"{i}. [{f.severity}] {f.file}:{f.line} {f.summary}"
        for i, f in enumerate(findings)
    )
    numbered = "\n".join(f"{i}. {b}" for i, b in enumerate(bugs))
    reply = JudgeReply.model_validate_json(
        extract_json(
            claude(
                JUDGE_PROMPT.format(bugs=numbered, findings=listed), JUDGE_MODEL, ROOT
            )
        )
    )
    labels = ["missed"] * len(bugs)
    for match in reply.matches:
        index = match.finding
        if (
            index is None
            or not 0 <= index < len(findings)
            or not 0 <= match.bug < len(bugs)
        ):
            continue
        important = findings[index].severity.lower() == "important"
        labels[match.bug] = "important" if important else "other"
    return labels


def run_item(item: Item, model: str, variant: str) -> Result:
    bugs = [bug.description for bug in item.bugs]
    result = Result(id=item.id, sha=item.commit, bugs=bugs)
    start = time.monotonic()
    try:
        result.findings = review(item.commit, model, variant)
        result.caught = judge(bugs, result.findings) if bugs else []
    except (subprocess.SubprocessError, ValueError, KeyError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"[:300]
    result.seconds = round(time.monotonic() - start, 1)
    return result


def important_count(result: Result) -> int:
    return sum(f.severity.lower() == "important" for f in result.findings)


def report(cases: list[Result], controls: list[Result]) -> str:
    lines = [
        f"{'case':28} {'bugs':>4} {'caught':>6} {'other':>5} {'findings':>8}  error"
    ]
    for r in cases + controls:
        lines.append(
            f"{r.id:28} {len(r.bugs):4d} {r.caught.count('important'):6d} "
            f"{r.caught.count('other'):5d} {len(r.findings):8d}  {r.error}"
        )
    bugs = sum(len(r.bugs) for r in cases)
    caught = sum(r.caught.count("important") for r in cases)
    noise = sum(important_count(r) for r in controls)
    lines.append(f"\nRecall: {caught}/{bugs} known bugs caught as Important")
    lines.append(f"Noise: {noise} Important findings on {len(controls)} clean PRs")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="case or control ids to run")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--model", default="opus", help="reviewer model")
    parser.add_argument("--prompt", choices=sorted(PROMPTS), default="single")
    args = parser.parse_args()

    spec = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    items = [
        (kind, Item.model_validate(raw))
        for kind in ("cases", "controls")
        for raw in spec[kind]
    ]
    if args.only:
        items = [(kind, item) for kind, item in items if item.id in args.only]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(
            pool.map(
                lambda pair: (pair[0], run_item(pair[1], args.model, args.prompt)),
                items,
            )
        )
    cases = [r for kind, r in results if kind == "cases"]
    controls = [r for kind, r in results if kind == "controls"]

    text = report(cases, controls)
    print(text)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.model}-{args.prompt}.json"
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "review_md": git("hash-object", "REVIEW.md").strip(),
        "results": [r.model_dump() for _, r in results],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
