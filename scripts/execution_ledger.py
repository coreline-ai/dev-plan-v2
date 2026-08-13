#!/usr/bin/env python3
"""Create, update, and verify a small JSON execution ledger for a plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from check_parallel_scope import check as check_scope
from check_parallel_scope import change_fingerprint
from check_parallel_scope import collect_changes
from parallel_plan_lib import json_text, load_json, plan_units, validate_plan

LEDGER_SCHEMA = "parallel-dev-execution/v1"
UNIT_STATES = {"pending", "passed", "failed", "blocked"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(json_text(value))
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def git_commit(repo: Path, revision: str) -> str:
    checked = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{revision}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if checked.returncode:
        raise ValueError(f"Git commit cannot be resolved: {revision}")
    return checked.stdout.strip()


def load_plan_checked(path: Path) -> dict[str, Any]:
    plan = load_json(path)
    errors = validate_plan(plan)
    if errors:
        raise ValueError("invalid plan: " + "; ".join(errors))
    return plan


def initialise(plan_path: Path, output: Path, repo: Path, baseline: str, common_commit: str | None) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"execution ledger already exists: {output}")
    plan = load_plan_checked(plan_path)
    baseline_hash = git_commit(repo, baseline)
    if plan.get("common"):
        lane_baseline = git_commit(repo, common_commit) if common_commit else None
    else:
        lane_baseline = baseline_hash
    units = {
        unit["id"]: {
            "state": "pending",
            "risk": unit["risk"],
            "repo": None,
            "commit": None,
            "scope_status": None,
            "scope_baseline": None,
            "scope_files": [],
            "scope_fingerprint": None,
            "tests": [],
            "qa": None,
            "reviewer": None,
            "requested_model": None,
            "actual_model": None,
            "updated_at": None,
        }
        for unit in plan_units(plan)
    }
    ledger = {
        "schema": LEDGER_SCHEMA,
        "plan_id": plan["plan_id"],
        "plan_path": str(plan_path),
        "plan_sha256": sha256(plan_path),
        "initial_baseline": baseline_hash,
        "common_commit": lane_baseline if plan.get("common") else None,
        "lane_baseline": lane_baseline,
        "units": units,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    atomic_write(output, ledger)
    return ledger


def parse_test_results(raw_results: list[str]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for raw in raw_results:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid --test-result JSON: {exc.msg}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("command"), str) or not isinstance(value.get("exit_code"), int):
            raise ValueError('--test-result must be {"command":"...","exit_code":0}')
        results.append({"command": value["command"], "exit_code": value["exit_code"]})
    return results


def qa_valid(risk: str, qa: str, reviewer: str) -> bool:
    if risk == "low":
        return qa in {"PASS", "NOT_REQUIRED"} and reviewer in {"lead", "independent", "specialist", "user"}
    if risk in {"medium", "high"}:
        return qa == "PASS" and reviewer in {"independent", "specialist", "user"}
    return qa == "PASS" and reviewer in {"specialist", "user"}


def record_unit(
    ledger_path: Path,
    scope_unit: str,
    repo: Path,
    revision: str,
    scope_baseline: str | None,
    tests: list[dict[str, object]],
    qa: str,
    reviewer: str,
    requested_model: str | None,
    actual_model: str | None,
) -> dict[str, Any]:
    ledger = load_json(ledger_path)
    if not isinstance(ledger, dict) or ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError("invalid execution ledger")
    plan_path = Path(ledger["plan_path"])
    if not plan_path.is_file() or sha256(plan_path) != ledger.get("plan_sha256"):
        raise ValueError("plan JSON changed after ledger creation")
    plan = load_plan_checked(plan_path)
    record = ledger.get("units", {}).get(scope_unit)
    if not isinstance(record, dict):
        raise ValueError(f"scope unit is not declared in the ledger: {scope_unit}")
    unit = next(item for item in plan_units(plan) if item["id"] == scope_unit)
    if scope_unit == "COMMON":
        required_units: list[str] = []
        baseline = str(ledger["initial_baseline"])
    elif scope_unit == "INTEGRATION":
        required_units = [item["id"] for item in plan["workstreams"]]
        if not scope_baseline:
            raise ValueError("INTEGRATION record requires --scope-baseline from immediately before integration work")
        baseline = scope_baseline
    else:
        required_units = list(unit["depends_on"])
        if ledger.get("lane_baseline") is None:
            raise ValueError("lane baseline is unavailable; COMMON must pass first")
        baseline = str(ledger["lane_baseline"])
    not_ready = [item for item in required_units if ledger["units"].get(item, {}).get("state") != "passed"]
    if not_ready:
        raise ValueError(f"scope unit dependencies have not passed: {', '.join(not_ready)}")
    declared_tests = set(unit["tests"])
    reported_tests = {str(item["command"]) for item in tests}
    tests_ok = declared_tests == reported_tests and all(item["exit_code"] == 0 for item in tests)
    collected_changes = collect_changes(repo, baseline)
    scope_status, scope_files = check_scope(plan, scope_unit, collected_changes)
    scope_fingerprint = change_fingerprint(repo, baseline, collected_changes)
    scope_ok = scope_status == "SCOPE_OK" or (scope_unit == "INTEGRATION" and not unit["write_paths"] and scope_status == "SCOPE_EMPTY")
    qa_ok = qa_valid(unit["risk"], qa, reviewer)
    compliance = bool(plan.get("compliance", {}).get("require_actual_model", False))
    model_ok = not compliance or bool(requested_model and actual_model and requested_model == actual_model)
    commit_hash = git_commit(repo, revision)
    if commit_hash != git_commit(repo, "HEAD"):
        raise ValueError("recorded commit must be the current worktree HEAD")
    if scope_ok and tests_ok and qa_ok and model_ok:
        state = "passed"
    elif qa == "BLOCKED" or not model_ok:
        state = "blocked"
    else:
        state = "failed"
    record.update(
        {
            "state": state,
            "repo": str(repo),
            "commit": commit_hash,
            "scope_status": scope_status,
            "scope_baseline": baseline,
            "scope_files": scope_files,
            "scope_fingerprint": scope_fingerprint,
            "tests": tests,
            "qa": qa,
            "reviewer": reviewer,
            "requested_model": requested_model,
            "actual_model": actual_model,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    if scope_unit == "COMMON" and state == "passed":
        ledger["common_commit"] = commit_hash
        ledger["lane_baseline"] = commit_hash
    ledger["updated_at"] = record["updated_at"]
    atomic_write(ledger_path, ledger)
    return ledger


def status(ledger_path: Path, verify_git: bool) -> dict[str, Any]:
    ledger = load_json(ledger_path)
    if not isinstance(ledger, dict) or ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError("invalid execution ledger")
    errors: list[str] = []
    plan_path = Path(ledger["plan_path"])
    plan: dict[str, Any] | None = None
    if not plan_path.is_file() or sha256(plan_path) != ledger.get("plan_sha256"):
        errors.append("plan JSON differs from the ledger source")
    else:
        try:
            plan = load_plan_checked(plan_path)
        except ValueError as exc:
            errors.append(str(exc))
    for unit_id, record in ledger.get("units", {}).items():
        if record.get("state") not in UNIT_STATES:
            errors.append(f"{unit_id} has an invalid state")
        if verify_git and record.get("state") == "passed":
            repo_text, revision = record.get("repo"), record.get("commit")
            if not repo_text or not revision:
                errors.append(f"{unit_id} is passed without Git evidence")
            else:
                try:
                    repo = Path(repo_text)
                    resolved = git_commit(repo, str(revision))
                    if git_commit(repo, "HEAD") != resolved:
                        errors.append(f"{unit_id} worktree HEAD differs from recorded commit")
                    if plan is not None:
                        baseline = record.get("scope_baseline")
                        if not baseline:
                            errors.append(f"{unit_id} is passed without a scope baseline")
                        else:
                            current_changes = collect_changes(repo, str(baseline))
                            current_status, current_files = check_scope(plan, unit_id, current_changes)
                            current_fingerprint = change_fingerprint(repo, str(baseline), current_changes)
                            if (
                                current_status != record.get("scope_status")
                                or current_files != record.get("scope_files")
                                or current_fingerprint != record.get("scope_fingerprint")
                            ):
                                errors.append(f"{unit_id} Git diff differs from recorded scope evidence")
                except ValueError as exc:
                    errors.append(f"{unit_id}: {exc}")
    states = {unit_id: record.get("state") for unit_id, record in ledger.get("units", {}).items()}
    if errors:
        result = "RESUME_BLOCKED"
    elif states and all(value == "passed" for value in states.values()):
        result = "EXECUTION_COMPLETE"
    elif any(value in {"failed", "blocked"} for value in states.values()):
        result = "EXECUTION_NEEDS_ATTENTION"
    else:
        result = "EXECUTION_PENDING"
    return {"status": result, "states": states, "errors": errors}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="병렬 계획 실행 사실을 작은 JSON ledger로 기록합니다.")
    sub = result.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--plan", required=True)
    init.add_argument("--output")
    init.add_argument("--repo", default=".")
    init.add_argument("--baseline", default="HEAD")
    init.add_argument("--common-commit")
    record = sub.add_parser("record-unit")
    record.add_argument("ledger")
    record.add_argument("--scope-unit", required=True)
    record.add_argument("--repo", required=True)
    record.add_argument("--commit", default="HEAD")
    record.add_argument("--scope-baseline", help="INTEGRATION 시작 직전 commit; COMMON/Workstream은 ledger에서 결정")
    record.add_argument("--test-result", action="append", default=[])
    record.add_argument("--qa", choices=("PASS", "FIX", "BLOCKED", "NOT_REQUIRED"), required=True)
    record.add_argument("--reviewer", choices=("lead", "independent", "specialist", "user"), required=True)
    record.add_argument("--requested-model")
    record.add_argument("--actual-model")
    show = sub.add_parser("status")
    show.add_argument("ledger")
    show.add_argument("--verify-git", action="store_true")
    for command in (init, record, show):
        command.add_argument("--format", choices=("text", "json"), default="text")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            plan_path = Path(args.plan).expanduser().resolve()
            output = Path(args.output).expanduser().resolve() if args.output else plan_path.with_suffix(".execution.json")
            ledger = initialise(plan_path, output, Path(args.repo).expanduser().resolve(), args.baseline, args.common_commit)
            report: dict[str, Any] = {"status": "LEDGER_CREATED", "path": str(output), "units": list(ledger["units"])}
            code = 0
        elif args.command == "record-unit":
            ledger_path = Path(args.ledger).expanduser().resolve()
            ledger = record_unit(
                ledger_path,
                args.scope_unit,
                Path(args.repo).expanduser().resolve(),
                args.commit,
                args.scope_baseline,
                parse_test_results(args.test_result),
                args.qa,
                args.reviewer,
                args.requested_model,
                args.actual_model,
            )
            state = ledger["units"][args.scope_unit]["state"]
            report = {"status": "UNIT_RECORDED", "scope_unit": args.scope_unit, "state": state, "path": str(ledger_path)}
            code = 0 if state == "passed" else 1
        else:
            report = status(Path(args.ledger).expanduser().resolve(), args.verify_git)
            code = 1 if report["status"] in {"RESUME_BLOCKED", "EXECUTION_NEEDS_ATTENTION"} else 0
    except (OSError, UnicodeError, ValueError) as exc:
        report = {"status": "LEDGER_ERROR", "error": str(exc)}
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
