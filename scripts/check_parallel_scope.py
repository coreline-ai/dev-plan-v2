#!/usr/bin/env python3
"""Check one scope unit against the complete Git change set of its worktree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from parallel_plan_lib import load_json, path_matches, plan_units, validate_plan


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _text(value: bytes) -> str:
    return value.decode("utf-8", "replace")


def _git_path(value: bytes) -> str:
    path = _text(value)
    if not path or path.startswith(("/", "~")) or ".." in path.split("/"):
        raise ValueError(f"Git returned an unsafe repository path: {path!r}")
    return path


def collect_changes(repo: Path, baseline: str) -> list[dict[str, str]]:
    resolved = git(repo, "rev-parse", "--verify", f"{baseline}^{{commit}}")
    if resolved.returncode:
        raise ValueError(f"Git baseline cannot be resolved: {baseline}")
    changed = git(repo, "diff", "-M", "--name-status", "-z", resolved.stdout.strip().decode("ascii"), "--")
    if changed.returncode:
        raise ValueError(_text(changed.stderr).strip() or "git diff failed")
    tokens = changed.stdout.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    details: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        status = _text(tokens[index])
        index += 1
        if not status:
            raise ValueError("git diff returned an empty status")
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                raise ValueError("git diff returned an incomplete rename/copy record")
            old_path, new_path = _git_path(tokens[index]), _git_path(tokens[index + 1])
            index += 2
            details.append({"status": status, "role": "old", "path": old_path})
            details.append({"status": status, "role": "new", "path": new_path})
        else:
            if index >= len(tokens):
                raise ValueError("git diff returned an incomplete path record")
            details.append({"status": status, "role": "path", "path": _git_path(tokens[index])})
            index += 1
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked.returncode:
        raise ValueError(_text(untracked.stderr).strip() or "git ls-files failed")
    for raw in untracked.stdout.split(b"\0"):
        if raw:
            details.append({"status": "??", "role": "untracked", "path": _git_path(raw)})
    return details


def change_fingerprint(repo: Path, baseline: str, changes: list[dict[str, str]]) -> str:
    """Hash tracked diff bytes plus untracked path/content for resume verification."""
    resolved = git(repo, "rev-parse", "--verify", f"{baseline}^{{commit}}")
    if resolved.returncode:
        raise ValueError(f"Git baseline cannot be resolved: {baseline}")
    diff = git(repo, "diff", "--binary", resolved.stdout.strip().decode("ascii"), "--")
    if diff.returncode:
        raise ValueError(_text(diff.stderr).strip() or "git diff fingerprint failed")
    digest = hashlib.sha256(diff.stdout)
    for change in sorted((item for item in changes if item["status"] == "??"), key=lambda item: item["path"]):
        relative = change["path"]
        path = repo / relative
        digest.update(b"\0untracked\0")
        digest.update(relative.encode("utf-8", "surrogatepass"))
        if path.is_symlink():
            digest.update(b"\0symlink\0")
            digest.update(os.readlink(path).encode("utf-8", "surrogatepass"))
        else:
            digest.update(b"\0file\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def effective_unit(units: list[dict[str, Any]], requested: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if requested.startswith("REWORK-"):
        base_id = requested.removeprefix("REWORK-")
        base = next((unit for unit in units if unit["id"] == base_id and base_id.startswith("WS-")), None)
        if base is None:
            raise ValueError(f"REWORK target workstream does not exist: {requested}")
        rework = {**base, "id": requested}
        ownership = [rework if unit["id"] == base_id else unit for unit in units]
        return rework, ownership
    current = next((unit for unit in units if unit["id"] == requested), None)
    if current is None:
        raise ValueError(f"scope unit does not exist: {requested}")
    return current, units


def check(plan: dict[str, Any], requested: str, changes: list[dict[str, str]]) -> tuple[str, list[dict[str, object]]]:
    current, ownership_units = effective_unit(plan_units(plan), requested)
    results: list[dict[str, object]] = []
    ambiguous = False
    violation = False
    for change in changes:
        path = change["path"]
        owners = [
            unit["id"]
            for unit in ownership_units
            if any(path_matches(path, owned) for owned in unit["write_paths"])
        ]
        excluded = any(path_matches(path, blocked) for blocked in current["exclude_paths"])
        if len(owners) > 1:
            outcome = "ambiguous"
            ambiguous = True
        elif current["id"] not in owners or excluded:
            outcome = "violation"
            violation = True
        else:
            outcome = "ok"
        results.append({**change, "owners": owners, "outcome": outcome})
    if ambiguous:
        return "SCOPE_AMBIGUOUS", results
    if violation:
        return "SCOPE_VIOLATION", results
    if not results:
        return "SCOPE_EMPTY", results
    return "SCOPE_OK", results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="한 scope unit의 실제 Git 변경 전체를 계획 write 경로와 대조합니다.")
    parser.add_argument("--plan", required=True, help="parallel-dev-plan/v3 JSON")
    parser.add_argument("--scope-unit", required=True, help="WS-01, COMMON, INTEGRATION 또는 REWORK-WS-01")
    parser.add_argument("--repo", default=".", help="검사할 Worker worktree root")
    parser.add_argument("--baseline", required=True, help="lane baseline commit")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        plan = load_json(Path(args.plan).expanduser().resolve())
        errors = validate_plan(plan)
        if errors:
            raise ValueError("invalid plan: " + "; ".join(errors))
        repo = Path(args.repo).expanduser().resolve()
        top = git(repo, "rev-parse", "--show-toplevel")
        if top.returncode or Path(_text(top.stdout).strip()).resolve() != repo:
            raise ValueError("--repo must be a Git worktree root")
        changes = collect_changes(repo, args.baseline)
        status, files = check(plan, args.scope_unit, changes)
        report: dict[str, object] = {
            "status": status,
            "scope_unit": args.scope_unit,
            "baseline": args.baseline,
            "repo": str(repo),
            "files": files,
        }
        code = 0 if status == "SCOPE_OK" else 1
    except (OSError, UnicodeError, ValueError) as exc:
        report = {"status": "SCOPE_AMBIGUOUS", "scope_unit": args.scope_unit, "error": str(exc), "files": []}
        code = 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["status"])
        if report.get("error"):
            print(f"- {report['error']}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
