#!/usr/bin/env python3
"""Verify the separately installed V1 Dev Lesson capability contract."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


EXPECTED_CAPABILITY = "dev-lesson-tool/v1"
EXPECTED_LESSON_SCHEMA = "dev-lesson/v1"
REQUIRED_COMMANDS = {"find", "record", "validate"}
REQUIRED_FEATURES = {"repo_path", "v2_evidence", "advisory_only"}


def default_skill_dir() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return codex_home / "skills" / "dev-plan-generator"


def check(skill_dir: Path) -> dict[str, object]:
    script = skill_dir.resolve() / "scripts/dev_lesson.py"
    if not script.is_file():
        return {"status": "LESSON_TOOL_UNAVAILABLE", "skill_dir": str(skill_dir), "error": "scripts/dev_lesson.py not found"}
    completed = subprocess.run(
        [sys.executable, str(script), "capabilities", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode:
        return {
            "status": "LESSON_TOOL_UNAVAILABLE",
            "skill_dir": str(skill_dir),
            "error": (completed.stdout + completed.stderr).strip() or f"capability command exited {completed.returncode}",
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "LESSON_TOOL_INCOMPATIBLE", "skill_dir": str(skill_dir), "error": f"invalid capability JSON: {exc.msg}"}
    commands = set(payload.get("commands", [])) if isinstance(payload.get("commands"), list) else set()
    features = set(payload.get("features", [])) if isinstance(payload.get("features"), list) else set()
    errors: list[str] = []
    if payload.get("capability_schema") != EXPECTED_CAPABILITY:
        errors.append(f"capability_schema must be {EXPECTED_CAPABILITY}")
    if payload.get("lesson_schema") != EXPECTED_LESSON_SCHEMA:
        errors.append(f"lesson_schema must be {EXPECTED_LESSON_SCHEMA}")
    if not REQUIRED_COMMANDS.issubset(commands):
        errors.append(f"missing commands: {', '.join(sorted(REQUIRED_COMMANDS - commands))}")
    if not REQUIRED_FEATURES.issubset(features):
        errors.append(f"missing features: {', '.join(sorted(REQUIRED_FEATURES - features))}")
    if errors:
        return {"status": "LESSON_TOOL_INCOMPATIBLE", "skill_dir": str(skill_dir), "errors": errors, "capabilities": payload}
    return {"status": "LESSON_TOOL_READY", "skill_dir": str(skill_dir.resolve()), "script": str(script), "capabilities": payload}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the V1 Dev Lesson capability required by the V2 adapter.")
    parser.add_argument("--skill-dir", default=str(default_skill_dir()))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        report = check(Path(args.skill_dir).expanduser())
    except (OSError, subprocess.SubprocessError) as exc:
        report = {"status": "LESSON_TOOL_UNAVAILABLE", "skill_dir": args.skill_dir, "error": str(exc)}
    code = 0 if report["status"] == "LESSON_TOOL_READY" else 1
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["status"])
        for error in report.get("errors", []):
            print(f"- {error}", file=sys.stderr)
        if report.get("error"):
            print(f"- {report['error']}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
