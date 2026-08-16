#!/usr/bin/env python3
"""Create and validate immutable post-QA lesson outcome sidecars."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from check_parallel_scope import check as check_scope
from execution_ledger import LEDGER_SCHEMA, git_commit, qa_valid
from parallel_plan_lib import load_json, plan_units, validate_plan


OUTCOMES_SCHEMA = "parallel-dev-outcomes/v1"
LESSON_ID = re.compile(r"^DL-\d{8}T\d{6}Z-[0-9a-f]{8}$")
UNIT_ID = re.compile(r"^(?:COMMON|INTEGRATION|WS-(?:0[1-9]|[1-9][0-9]))$")
SENSITIVE = re.compile(
    r"(?:authorization\s*:\s*(?:bearer|basic)\s+\S+|(?:set-)?cookie\s*:\s*\S+|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|"
    r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b)",
    re.I,
)
OUTCOME_FIELDS = {
    "schema", "plan_id", "plan_file", "plan_sha256", "ledger_file", "ledger_sha256",
    "created_at", "lesson_tool", "verified_lessons", "prior_lessons", "occurrences",
}
LEDGER_FIELDS = {
    "schema", "plan_id", "plan_path", "plan_sha256", "initial_baseline", "common_commit",
    "lane_baseline", "units", "created_at", "updated_at",
}
UNIT_FIELDS = {
    "state", "risk", "repo", "commit", "scope_status", "scope_baseline", "scope_files",
    "scope_fingerprint", "tests", "qa", "reviewer", "requested_model", "actual_model", "updated_at",
}
CAPABILITY_SCHEMA = "dev-lesson-tool/v1"
LESSON_SCHEMA = "dev-lesson/v1"
REQUIRED_COMMANDS = {"find", "record", "validate"}
REQUIRED_FEATURES = {"repo_path", "v2_evidence", "advisory_only"}
GIT_OBJECT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def strings(value: Any, field: str, *, required: bool = False) -> list[str]:
    require(isinstance(value, list), f"{field} must be a list")
    result: list[str] = []
    for item in value:
        require(isinstance(item, str) and item.strip() != "", f"{field} accepts non-empty strings only")
        cleaned = item.strip()
        require(cleaned not in result, f"{field} contains a duplicate: {cleaned}")
        result.append(cleaned)
    require(not required or bool(result), f"{field} requires at least one value")
    return result


def require_redacted(value: Any) -> None:
    if isinstance(value, str):
        require(SENSITIVE.search(value) is None, "Outcome content contains unredacted sensitive data")
    elif isinstance(value, list):
        for item in value:
            require_redacted(item)
    elif isinstance(value, dict):
        for item in value.values():
            require_redacted(item)


def validate_lesson_tool(value: Any) -> dict[str, str]:
    require(isinstance(value, dict) and set(value) == {"status", "detail"}, "lesson_tool requires status and detail")
    require(value["status"] in {"AVAILABLE", "LESSON_TOOL_UNAVAILABLE"}, "Invalid lesson_tool status")
    require(isinstance(value["detail"], str) and value["detail"].strip() != "", "lesson_tool.detail is required")
    return {"status": value["status"], "detail": value["detail"].strip()}


def validate_prior_lessons(value: Any) -> list[dict[str, Any]]:
    require(isinstance(value, list), "prior_lessons must be a list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    fields = {"lesson_id", "disposition", "reason", "control", "task_refs", "test_refs", "waiver"}
    for item in value:
        require(isinstance(item, dict) and set(item) == fields, "prior lesson fields mismatch")
        lesson_id = item["lesson_id"]
        require(isinstance(lesson_id, str) and LESSON_ID.fullmatch(lesson_id) is not None, "Invalid prior lesson id")
        require(lesson_id not in seen, f"Duplicate prior lesson disposition: {lesson_id}")
        seen.add(lesson_id)
        disposition = item["disposition"]
        require(disposition in {"adopted", "not-applicable", "waived"}, "Invalid prior lesson disposition")
        require(isinstance(item["reason"], str) and item["reason"].strip() != "", "Prior lesson reason is required")
        task_refs = strings(item["task_refs"], "prior_lessons.task_refs")
        test_refs = strings(item["test_refs"], "prior_lessons.test_refs")
        control = item["control"]
        require(control is None or isinstance(control, str), "Prior lesson control must be null or string")
        waiver = item["waiver"]
        if disposition == "adopted":
            require(isinstance(control, str) and control.strip() != "", "adopted requires a prevention control")
            require(bool(task_refs) and bool(test_refs), "adopted requires task_refs and test_refs")
            require(waiver is None, "adopted cannot have a waiver")
        elif disposition == "not-applicable":
            require(control is None and not task_refs and not test_refs and waiver is None, "not-applicable only records its scope reason")
        else:
            waiver_fields = {"reason", "approver", "expiry", "compensating_control"}
            require(isinstance(waiver, dict) and set(waiver) == waiver_fields, "waived requires reason, approver, expiry, and compensating_control")
            require(all(isinstance(waiver[field], str) and waiver[field].strip() for field in waiver_fields), "waiver fields must be non-empty strings")
            waiver = {field: waiver[field].strip() for field in waiver_fields}
        result.append({
            "lesson_id": lesson_id,
            "disposition": disposition,
            "reason": item["reason"].strip(),
            "control": control.strip() if isinstance(control, str) else None,
            "task_refs": task_refs,
            "test_refs": test_refs,
            "waiver": waiver,
        })
    return result


def validate_occurrences(value: Any, known_units: set[str], tool_status: str) -> list[dict[str, Any]]:
    require(isinstance(value, list), "occurrences must be a list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    fields = {
        "occurrence_id", "source_units", "summary", "impact", "evidence", "temporary_action",
        "disposition", "reason", "lesson_id", "durable_refs",
    }
    for item in value:
        require(isinstance(item, dict) and set(item) == fields, "occurrence fields mismatch")
        occurrence_id = item["occurrence_id"]
        require(isinstance(occurrence_id, str) and occurrence_id.strip() != "", "occurrence_id is required")
        require(occurrence_id not in seen, f"Duplicate occurrence_id: {occurrence_id}")
        seen.add(occurrence_id)
        source_units = strings(item["source_units"], "occurrence.source_units", required=True)
        require(all(UNIT_ID.fullmatch(unit) and unit in known_units for unit in source_units), "occurrence contains an unknown source unit")
        for field in ("summary", "impact", "evidence", "temporary_action", "reason"):
            require(isinstance(item[field], str) and item[field].strip() != "", f"occurrence.{field} is required")
        disposition = item["disposition"]
        require(disposition in {"plan-only", "existing-reference", "new-lesson", "record-pending"}, "Invalid occurrence disposition")
        lesson_id = item["lesson_id"]
        require(lesson_id is None or (isinstance(lesson_id, str) and LESSON_ID.fullmatch(lesson_id)), "Invalid occurrence lesson_id")
        if disposition in {"existing-reference", "new-lesson"}:
            require(isinstance(lesson_id, str), f"{disposition} requires lesson_id")
        else:
            require(lesson_id is None, f"{disposition} cannot claim lesson_id")
        if disposition == "record-pending":
            require(tool_status == "LESSON_TOOL_UNAVAILABLE", "record-pending requires LESSON_TOOL_UNAVAILABLE")
        durable_refs = strings(item["durable_refs"], "occurrence.durable_refs")
        result.append({
            **item,
            "occurrence_id": occurrence_id.strip(),
            "source_units": source_units,
            "summary": item["summary"].strip(),
            "impact": item["impact"].strip(),
            "evidence": item["evidence"].strip(),
            "temporary_action": item["temporary_action"].strip(),
            "reason": item["reason"].strip(),
            "durable_refs": durable_refs,
        })
    return result


def validate_input(spec: Any, known_units: set[str]) -> dict[str, Any]:
    require(isinstance(spec, dict) and set(spec) == {"lesson_tool", "prior_lessons", "occurrences"}, "Outcome input requires lesson_tool, prior_lessons, and occurrences")
    lesson_tool = validate_lesson_tool(spec["lesson_tool"])
    normalized = {
        "lesson_tool": lesson_tool,
        "prior_lessons": validate_prior_lessons(spec["prior_lessons"]),
        "occurrences": validate_occurrences(spec["occurrences"], known_units, lesson_tool["status"]),
    }
    require_redacted(normalized)
    return normalized


def require_timestamp(value: Any, field: str) -> None:
    require(isinstance(value, str) and value.strip() != "", f"{field} is required")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc


def validate_scope_files(value: Any, field: str) -> list[dict[str, Any]]:
    require(isinstance(value, list), f"{field} must be a list")
    result: list[dict[str, Any]] = []
    for item in value:
        required = {"status", "role", "path", "owners", "outcome"}
        require(isinstance(item, dict) and set(item) == required, f"{field} entry fields mismatch")
        require(all(isinstance(item[key], str) and item[key] for key in ("status", "role", "path", "outcome")), f"{field} string fields are required")
        require(item["outcome"] == "ok", f"{field} contains a non-compliant path")
        owners = strings(item["owners"], f"{field}.owners", required=True)
        result.append({**item, "owners": owners})
    return result


def git_bytes(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    require(completed.returncode == 0, completed.stderr.decode("utf-8", "replace").strip() or "Git evidence command failed")
    return completed.stdout


def git_path(raw: bytes) -> str:
    value = raw.decode("utf-8", "replace")
    require(bool(value) and not value.startswith(("/", "~")) and ".." not in value.split("/"), f"Git returned an unsafe path: {value!r}")
    return value


def collect_commit_changes(repo: Path, baseline: str, commit: str) -> list[dict[str, str]]:
    tokens = git_bytes(repo, "diff", "-M", "--name-status", "-z", baseline, commit, "--").split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    result: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("utf-8", "replace")
        index += 1
        require(bool(status), "Git diff returned an empty status")
        if status.startswith(("R", "C")):
            require(index + 1 < len(tokens), "Git diff returned an incomplete rename/copy record")
            result.append({"status": status, "role": "old", "path": git_path(tokens[index])})
            result.append({"status": status, "role": "new", "path": git_path(tokens[index + 1])})
            index += 2
        else:
            require(index < len(tokens), "Git diff returned an incomplete path record")
            result.append({"status": status, "role": "path", "path": git_path(tokens[index])})
            index += 1
    return result


def commit_fingerprint(repo: Path, baseline: str, commit: str) -> str:
    return hashlib.sha256(git_bytes(repo, "diff", "--binary", baseline, commit, "--")).hexdigest()


def validate_completed_ledger(
    plan_path: Path,
    plan: dict[str, Any],
    ledger_path: Path,
    ledger: Any,
    *,
    verify_repository_objects: bool,
) -> set[str]:
    require(isinstance(ledger, dict) and set(ledger) == LEDGER_FIELDS, "Execution ledger fields mismatch")
    require(ledger["schema"] == LEDGER_SCHEMA, "Invalid execution ledger schema")
    require(ledger["plan_id"] == plan["plan_id"], "Ledger plan_id does not match plan")
    recorded_plan = Path(ledger["plan_path"]).expanduser().resolve() if isinstance(ledger["plan_path"], str) else None
    require(recorded_plan == plan_path, "Ledger plan_path does not match outcomes plan")
    require(ledger["plan_sha256"] == sha256(plan_path), "Ledger plan hash does not match plan")
    require(GIT_OBJECT.fullmatch(str(ledger["initial_baseline"])) is not None, "Ledger initial_baseline must be a full Git object id")
    require_timestamp(ledger["created_at"], "ledger.created_at")
    require_timestamp(ledger["updated_at"], "ledger.updated_at")

    declared = {unit["id"]: unit for unit in plan_units(plan)}
    units = ledger["units"]
    require(isinstance(units, dict) and set(units) == set(declared), "Ledger units must exactly match plan units")
    for unit_id, unit in declared.items():
        record = units[unit_id]
        require(isinstance(record, dict) and set(record) == UNIT_FIELDS, f"{unit_id} ledger fields mismatch")
        require(record["state"] == "passed", f"{unit_id} has not passed")
        require(record["risk"] == unit["risk"], f"{unit_id} risk differs from plan")
        require(isinstance(record["repo"], str) and record["repo"].strip(), f"{unit_id} is passed without repository evidence")
        require(isinstance(record["commit"], str) and GIT_OBJECT.fullmatch(record["commit"]) is not None, f"{unit_id} commit must be a full Git object id")
        require(isinstance(record["scope_baseline"], str) and GIT_OBJECT.fullmatch(record["scope_baseline"]) is not None, f"{unit_id} scope_baseline must be a full Git object id")
        allowed_scope = {"SCOPE_OK"}
        if unit_id == "INTEGRATION" and not unit["write_paths"]:
            allowed_scope.add("SCOPE_EMPTY")
        require(record["scope_status"] in allowed_scope, f"{unit_id} has invalid scope evidence")
        files = validate_scope_files(record["scope_files"], f"{unit_id}.scope_files")
        require(record["scope_status"] != "SCOPE_OK" or bool(files), f"{unit_id} SCOPE_OK requires changed files")
        require(record["scope_status"] != "SCOPE_EMPTY" or not files, f"{unit_id} SCOPE_EMPTY cannot contain files")
        require(isinstance(record["scope_fingerprint"], str) and SHA256.fullmatch(record["scope_fingerprint"]) is not None, f"{unit_id} scope_fingerprint must be SHA-256")
        tests = record["tests"]
        require(isinstance(tests, list) and all(isinstance(item, dict) and set(item) == {"command", "exit_code"} for item in tests), f"{unit_id} test evidence fields mismatch")
        require([item["command"] for item in tests] == unit["tests"], f"{unit_id} test commands differ from plan")
        require(all(item["exit_code"] == 0 for item in tests), f"{unit_id} has a failed test")
        require(isinstance(record["qa"], str) and isinstance(record["reviewer"], str) and qa_valid(unit["risk"], record["qa"], record["reviewer"]), f"{unit_id} QA/reviewer evidence is insufficient")
        require_timestamp(record["updated_at"], f"{unit_id}.updated_at")
        for model_field in ("requested_model", "actual_model"):
            require(record[model_field] is None or isinstance(record[model_field], str), f"{unit_id}.{model_field} must be null or string")
        if plan.get("compliance", {}).get("require_actual_model"):
            require(bool(record["requested_model"]) and record["requested_model"] == record["actual_model"], f"{unit_id} model compliance evidence is invalid")
        if verify_repository_objects:
            repo = Path(record["repo"]).expanduser().resolve()
            require(repo.is_dir(), f"{unit_id} repository is unavailable: {repo}")
            require(git_commit(repo, record["commit"]) == record["commit"], f"{unit_id} commit cannot be resolved")
            require(git_commit(repo, record["scope_baseline"]) == record["scope_baseline"], f"{unit_id} scope baseline cannot be resolved")
            require(git_commit(repo, "HEAD") == record["commit"], f"{unit_id} worktree HEAD differs from recorded commit")
            changes = collect_commit_changes(repo, record["scope_baseline"], record["commit"])
            recalculated_status, recalculated_files = check_scope(plan, unit_id, changes)
            recalculated_fingerprint = commit_fingerprint(repo, record["scope_baseline"], record["commit"])
            require(recalculated_status == record["scope_status"], f"{unit_id} scope status differs from committed Git evidence")
            require(recalculated_files == record["scope_files"], f"{unit_id} scope files differ from committed Git evidence")
            require(recalculated_fingerprint == record["scope_fingerprint"], f"{unit_id} scope fingerprint differs from committed Git evidence")

    if plan.get("common"):
        require(isinstance(ledger["common_commit"], str) and GIT_OBJECT.fullmatch(ledger["common_commit"]) is not None, "COMMON execution requires common_commit")
        require(ledger["lane_baseline"] == ledger["common_commit"], "lane_baseline must equal common_commit")
    else:
        require(ledger["common_commit"] is None, "common_commit must be null without COMMON")
        require(ledger["lane_baseline"] == ledger["initial_baseline"], "lane_baseline must equal initial_baseline")
    return set(units)


def verify_lesson_tool(script: Path) -> None:
    require(script.is_file() and not script.is_symlink(), f"Dev Lesson tool is unavailable: {script}")
    completed = subprocess.run(
        [sys.executable, str(script), "capabilities", "--format", "json"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    require(completed.returncode == 0, "Dev Lesson capability check failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Dev Lesson capability output is not JSON") from exc
    commands = set(payload.get("commands", [])) if isinstance(payload.get("commands"), list) else set()
    features = set(payload.get("features", [])) if isinstance(payload.get("features"), list) else set()
    require(payload.get("capability_schema") == CAPABILITY_SCHEMA, "Incompatible Dev Lesson capability schema")
    require(payload.get("lesson_schema") == LESSON_SCHEMA, "Incompatible Dev Lesson schema")
    require(REQUIRED_COMMANDS.issubset(commands) and REQUIRED_FEATURES.issubset(features), "Dev Lesson tool lacks required commands or features")


def verify_lesson_files(repo: Path, script: Path, lesson_ids: set[str]) -> list[dict[str, str]]:
    verified: list[dict[str, str]] = []
    for lesson_id in sorted(lesson_ids):
        relative = Path("docs/dev-lessons") / f"{lesson_id}.md"
        lesson = repo / relative
        require(lesson.is_file() and not lesson.is_symlink(), f"Claimed Lesson does not exist: {relative.as_posix()}")
        completed = subprocess.run(
            [sys.executable, str(script), "validate", str(lesson), "--root", str(repo), "--format", "json"],
            capture_output=True, text=True, check=False, timeout=30,
        )
        require(completed.returncode == 0, f"Claimed Lesson failed V1 validation: {lesson_id}")
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Claimed Lesson validation is not JSON: {lesson_id}") from exc
        lessons = report.get("lessons") if isinstance(report, dict) else None
        require(report.get("status") == "LESSON_VALID" and isinstance(lessons, list) and len(lessons) == 1, f"Claimed Lesson validation result is invalid: {lesson_id}")
        require(lessons[0].get("id") == lesson_id and lessons[0].get("repo_path") == relative.as_posix(), f"Claimed Lesson identity mismatch: {lesson_id}")
        verified.append({"lesson_id": lesson_id, "repo_path": relative.as_posix(), "sha256": sha256(lesson)})
    return verified


def validate_verified_lessons(value: Any, repo: Path, referenced_ids: set[str]) -> list[dict[str, str]]:
    require(isinstance(value, list), "verified_lessons must be a list")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        require(isinstance(item, dict) and set(item) == {"lesson_id", "repo_path", "sha256"}, "verified_lesson fields mismatch")
        lesson_id = item["lesson_id"]
        require(isinstance(lesson_id, str) and LESSON_ID.fullmatch(lesson_id) is not None and lesson_id not in seen, "Invalid or duplicate verified lesson id")
        expected_path = f"docs/dev-lessons/{lesson_id}.md"
        require(item["repo_path"] == expected_path, f"verified lesson path mismatch: {lesson_id}")
        require(isinstance(item["sha256"], str) and SHA256.fullmatch(item["sha256"]) is not None, f"verified lesson hash is invalid: {lesson_id}")
        lesson = repo / expected_path
        require(lesson.is_file() and not lesson.is_symlink() and sha256(lesson) == item["sha256"], f"verified Lesson changed or is missing: {lesson_id}")
        seen.add(lesson_id)
        result.append(item)
    require(seen == referenced_ids, "verified_lessons must exactly cover every claimed Lesson id")
    return result


def publish_exclusive(path: Path, payload: dict[str, Any]) -> None:
    require(not path.exists(), f"Refusing to overwrite outcomes sidecar: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    published = False
    try:
        os.link(temporary, path)
        published = True
        os.chmod(path, 0o644)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def create_outcomes(plan_path: Path, ledger_path: Path, spec: Any, output: Path, lesson_tool_script: Path | None) -> dict[str, Any]:
    plan_path, ledger_path, output = plan_path.resolve(), ledger_path.resolve(), output.resolve()
    require(plan_path.parent == ledger_path.parent == output.parent, "Plan, ledger, and outcomes must be adjacent")
    plan = load_json(plan_path)
    errors = validate_plan(plan)
    require(not errors, "Invalid plan: " + "; ".join(errors))
    repo = output.parents[2]
    require(output.parent.name == "parallel" and output.parent.parent.name == "dev-plan", "Outcomes must use <repo>/dev-plan/parallel")
    ledger = load_json(ledger_path)
    known_units = validate_completed_ledger(plan_path, plan, ledger_path, ledger, verify_repository_objects=True)
    normalized = validate_input(spec, known_units)
    referenced_ids = {item["lesson_id"] for item in normalized["prior_lessons"]}
    referenced_ids.update(item["lesson_id"] for item in normalized["occurrences"] if item["lesson_id"] is not None)
    if normalized["lesson_tool"]["status"] == "AVAILABLE":
        require(lesson_tool_script is not None, "AVAILABLE requires --lesson-tool-script")
        verify_lesson_tool(lesson_tool_script)
        references = plan.get("references", [])
        require(all(any(lesson_id in reference for reference in references) for lesson_id in {item["lesson_id"] for item in normalized["prior_lessons"]}), "Each prior Lesson must be present in plan references")
        verified_lessons = verify_lesson_files(repo, lesson_tool_script, referenced_ids)
    else:
        require(lesson_tool_script is None, "Unavailable tool cannot use --lesson-tool-script")
        require(not normalized["prior_lessons"] and not referenced_ids, "Unavailable tool cannot claim prior, existing, or newly recorded Lessons")
        verified_lessons = []
    payload = {
        "schema": OUTCOMES_SCHEMA,
        "plan_id": plan["plan_id"],
        "plan_file": plan_path.name,
        "plan_sha256": sha256(plan_path),
        "ledger_file": ledger_path.name,
        "ledger_sha256": sha256(ledger_path),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "verified_lessons": verified_lessons,
        **normalized,
    }
    publish_exclusive(output, payload)
    return payload


def validate_outcomes(path: Path, lesson_tool_script: Path | None) -> dict[str, Any]:
    path = path.resolve()
    payload = load_json(path)
    require(isinstance(payload, dict) and set(payload) == OUTCOME_FIELDS, "Outcomes fields mismatch")
    require(payload["schema"] == OUTCOMES_SCHEMA, f"schema must be {OUTCOMES_SCHEMA}")
    plan_path = path.parent / payload["plan_file"]
    ledger_path = path.parent / payload["ledger_file"]
    require(plan_path.is_file() and ledger_path.is_file(), "Outcomes source plan or ledger is missing")
    require(sha256(plan_path) == payload["plan_sha256"], "Outcomes plan hash mismatch")
    require(sha256(ledger_path) == payload["ledger_sha256"], "Outcomes ledger hash mismatch")
    repo = path.parents[2]
    require(path.parent.name == "parallel" and path.parent.parent.name == "dev-plan", "Outcomes must use <repo>/dev-plan/parallel")
    plan = load_json(plan_path)
    errors = validate_plan(plan)
    require(not errors, "Invalid plan: " + "; ".join(errors))
    ledger = load_json(ledger_path)
    require(payload["plan_id"] == plan.get("plan_id") == ledger.get("plan_id"), "Outcomes plan_id mismatch")
    require(isinstance(payload["created_at"], str) and payload["created_at"].strip() != "", "created_at is required")
    known_units = validate_completed_ledger(plan_path, plan, ledger_path, ledger, verify_repository_objects=False)
    normalized = validate_input(
        {key: payload[key] for key in ("lesson_tool", "prior_lessons", "occurrences")},
        known_units,
    )
    require(normalized == {key: payload[key] for key in normalized}, "Outcomes content is not normalized")
    referenced_ids = {item["lesson_id"] for item in normalized["prior_lessons"]}
    referenced_ids.update(item["lesson_id"] for item in normalized["occurrences"] if item["lesson_id"] is not None)
    persisted_verified = validate_verified_lessons(payload["verified_lessons"], repo, referenced_ids)
    if normalized["lesson_tool"]["status"] == "AVAILABLE":
        require(lesson_tool_script is not None, "AVAILABLE outcomes validation requires --lesson-tool-script")
        verify_lesson_tool(lesson_tool_script)
        require(verify_lesson_files(repo, lesson_tool_script, referenced_ids) == persisted_verified, "V1 Lesson revalidation differs from outcomes evidence")
    else:
        require(lesson_tool_script is None, "Unavailable tool cannot use --lesson-tool-script")
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Record immutable post-QA Dev Lesson dispositions without mutating a V2 plan or ledger.")
    sub = result.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--plan", required=True)
    create.add_argument("--ledger", required=True)
    create.add_argument("--input", required=True)
    create.add_argument("--output")
    create.add_argument("--lesson-tool-script", help="Compatible V1 scripts/dev_lesson.py; required when lesson_tool.status=AVAILABLE")
    validate = sub.add_parser("validate")
    validate.add_argument("outcomes")
    validate.add_argument("--lesson-tool-script", help="Compatible V1 scripts/dev_lesson.py; required for AVAILABLE outcomes")
    for command in (create, validate):
        command.add_argument("--format", choices=("text", "json"), default="text")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "create":
            plan = Path(args.plan).expanduser().resolve()
            ledger = Path(args.ledger).expanduser().resolve()
            output = Path(args.output).expanduser().resolve() if args.output else plan.with_suffix(".outcomes.json")
            spec = load_json(Path(args.input).expanduser().resolve())
            lesson_tool_script = Path(args.lesson_tool_script).expanduser().resolve() if args.lesson_tool_script else None
            payload = create_outcomes(plan, ledger, spec, output, lesson_tool_script)
            report = {"status": "OUTCOMES_CREATED", "path": str(output), "plan_id": payload["plan_id"]}
        else:
            output = Path(args.outcomes).expanduser().resolve()
            lesson_tool_script = Path(args.lesson_tool_script).expanduser().resolve() if args.lesson_tool_script else None
            payload = validate_outcomes(output, lesson_tool_script)
            report = {"status": "OUTCOMES_VALID", "path": str(output), "plan_id": payload["plan_id"]}
        code = 0
    except (OSError, UnicodeError, ValueError) as exc:
        report = {"status": "OUTCOMES_ERROR", "error": str(exc)}
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
