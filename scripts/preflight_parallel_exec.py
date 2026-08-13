#!/usr/bin/env python3
"""Perform non-destructive Git and plan checks before parallel execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from parallel_plan_lib import load_json, validate_plan


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def commit(repo: Path, revision: str) -> str:
    checked = git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if checked.returncode:
        raise ValueError(f"Git commit cannot be resolved: {revision}")
    return checked.stdout.decode("ascii").strip()


def preflight(repo: Path, plan_path: Path, baseline: str, common_commit: str | None) -> tuple[str, dict[str, object]]:
    plan = load_json(plan_path)
    errors = validate_plan(plan)
    if errors:
        return "PREFLIGHT_BLOCKED", {"errors": errors}
    top = git(repo, "rev-parse", "--show-toplevel")
    if top.returncode:
        return "PREFLIGHT_BLOCKED", {"errors": ["target is not a Git worktree"]}
    top_path = Path(top.stdout.decode("utf-8", "surrogateescape").strip()).resolve()
    if top_path != repo.resolve():
        return "PREFLIGHT_BLOCKED", {"errors": [f"--repo must be the worktree root: {top_path}"]}
    baseline_commit = commit(repo, baseline)
    staged = git(repo, "ls-files", "--stage", "-z")
    if staged.returncode:
        return "PREFLIGHT_BLOCKED", {"errors": ["cannot inspect Git index modes"], "baseline": baseline_commit}
    if any(record.startswith(b"160000 ") for record in staged.stdout.split(b"\0") if record):
        return "PREFLIGHT_BLOCKED", {
            "errors": ["Git submodules are not supported by the V2 scope checker"],
            "baseline": baseline_commit,
        }
    dirty = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if dirty.returncode:
        return "PREFLIGHT_BLOCKED", {"errors": [dirty.stderr.decode("utf-8", "replace").strip()]}
    if dirty.stdout:
        return "PREFLIGHT_BLOCKED", {
            "errors": ["worktree is not clean; preserve user changes explicitly before parallel execution"],
            "baseline": baseline_commit,
        }
    worktrees = git(repo, "worktree", "list", "--porcelain")
    if worktrees.returncode:
        return "PREFLIGHT_BLOCKED", {"errors": ["git worktree is not available"], "baseline": baseline_commit}
    if plan.get("common"):
        if not common_commit:
            return "PREFLIGHT_READY_COMMON_ONLY", {
                "baseline": baseline_commit,
                "lane_baseline": None,
                "next": "Complete and verify COMMON, then rerun with --common-commit.",
            }
        common_hash = commit(repo, common_commit)
        ancestor = git(repo, "merge-base", "--is-ancestor", baseline_commit, common_hash)
        if ancestor.returncode:
            return "PREFLIGHT_BLOCKED", {
                "errors": ["COMMON commit must descend from the initial baseline"],
                "baseline": baseline_commit,
                "common_commit": common_hash,
            }
        lane_baseline = common_hash
    else:
        lane_baseline = baseline_commit
    return "PREFLIGHT_READY", {
        "baseline": baseline_commit,
        "common_commit": common_commit and lane_baseline,
        "lane_baseline": lane_baseline,
        "workstreams": [unit["id"] for unit in plan["workstreams"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="병렬 실행 전 clean Git baseline과 worktree 사용 가능 여부를 검사합니다.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--baseline", default="HEAD")
    parser.add_argument("--common-commit")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        status, details = preflight(
            Path(args.repo).expanduser().resolve(),
            Path(args.plan).expanduser().resolve(),
            args.baseline,
            args.common_commit,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        status, details = "PREFLIGHT_BLOCKED", {"errors": [str(exc)]}
    report = {"status": status, **details}
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(status)
        for error in report.get("errors", []):
            print(f"- {error}", file=sys.stderr)
        if report.get("next"):
            print(f"- {report['next']}")
    return 0 if status.startswith("PREFLIGHT_READY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
