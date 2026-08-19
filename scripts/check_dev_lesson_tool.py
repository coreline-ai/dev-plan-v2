#!/usr/bin/env python3
"""Verify the separately installed V1 Dev Lesson capability contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


EXPECTED_CAPABILITY = "dev-lesson-tool/v1"
EXPECTED_LESSON_SCHEMA = "dev-lesson/v1"
REQUIRED_COMMANDS = {"find", "record", "validate"}
REQUIRED_FEATURES = {"repo_path", "v2_evidence", "advisory_only"}
V1_SKILL_NAME = "dev-plan-generator"
V2_SKILL_NAME = "parallel-dev-plan-orchestrator"
FRONTMATTER_NAME_RE = re.compile(r"(?m)^name:\s*['\"]?([a-z0-9-]+)['\"]?\s*$")


def default_skill_dir() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return codex_home / "skills" / "dev-plan-generator"


def default_skills_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return codex_home / "skills"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skill_name(skill_markdown: Path) -> str:
    text = skill_markdown.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("SKILL.md frontmatter is not closed")
    match = FRONTMATTER_NAME_RE.search(text[4:end])
    if not match:
        raise ValueError("SKILL.md frontmatter has no valid name")
    return match.group(1)


def _scan_installed_skills(skills_root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    root = skills_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Skills root is not a directory: {skills_root}")

    by_target: dict[Path, dict[str, object]] = {}
    issues: list[dict[str, object]] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        lexical_skill = entry / "SKILL.md"
        if not lexical_skill.is_file():
            continue
        try:
            name = _skill_name(lexical_skill)
            digest = _sha256(lexical_skill)
        except (OSError, UnicodeError, ValueError) as exc:
            if entry.name in {V1_SKILL_NAME, V2_SKILL_NAME}:
                issues.append({"code": "SKILL_METADATA_INVALID", "path": str(entry), "message": str(exc)})
            continue
        if name not in {V1_SKILL_NAME, V2_SKILL_NAME}:
            continue
        try:
            target = entry.resolve(strict=True)
        except OSError as exc:
            issues.append({"code": "SKILL_PATH_INVALID", "path": str(entry), "message": str(exc)})
            continue
        if not target.is_relative_to(root):
            issues.append(
                {
                    "code": "SKILL_PATH_ESCAPE",
                    "path": str(entry),
                    "target": str(target),
                    "message": "Installed skill resolves outside the skills root",
                }
            )
            continue

        existing = by_target.get(target)
        if existing is not None:
            aliases = existing["aliases"]
            assert isinstance(aliases, list)
            aliases.append(str(entry))
            continue
        by_target[target] = {
            "name": name,
            "path": str(target),
            "aliases": [str(entry)],
            "skill_sha256": digest,
        }
    return sorted(by_target.values(), key=lambda item: str(item["path"])), issues


def check_install_layout(skills_root: Path) -> dict[str, object]:
    requested_root = skills_root.expanduser()
    try:
        root = requested_root.resolve(strict=True)
        installations, issues = _scan_installed_skills(root)
    except (OSError, UnicodeError, ValueError) as exc:
        return {
            "status": "PLAN_SKILL_INSTALL_INVALID",
            "skills_root": str(requested_root),
            "issues": [{"code": "SKILLS_ROOT_INVALID", "path": str(requested_root), "message": str(exc)}],
            "installations": [],
        }

    canonical_v1 = root / V1_SKILL_NAME
    canonical_v2 = root / V2_SKILL_NAME
    relevant = [item for item in installations if item["name"] in {V1_SKILL_NAME, V2_SKILL_NAME}]

    def has_alias(path: Path, expected_name: str) -> bool:
        return any(str(path) in item["aliases"] and item["name"] == expected_name for item in relevant)

    if not has_alias(canonical_v1, V1_SKILL_NAME):
        issues.append(
            {
                "code": "V1_CANONICAL_MISSING",
                "path": str(canonical_v1),
                "message": "Install dev-plan-generator separately at the canonical path",
            }
        )
        lesson_tool: dict[str, object] = {
            "status": "LESSON_TOOL_UNAVAILABLE",
            "skill_dir": str(canonical_v1),
            "error": "canonical V1 skill is missing",
        }
    else:
        lesson_tool = check(canonical_v1)
        if lesson_tool["status"] != "LESSON_TOOL_READY":
            issues.append(
                {
                    "code": "V1_CAPABILITY_NOT_READY",
                    "path": str(canonical_v1),
                    "message": str(lesson_tool["status"]),
                }
            )

    if not has_alias(canonical_v2, V2_SKILL_NAME):
        issues.append(
            {
                "code": "V2_CANONICAL_MISSING",
                "path": str(canonical_v2),
                "message": "Install parallel-dev-plan-orchestrator at the canonical path",
            }
        )

    v2_installations = [item for item in relevant if item["name"] == V2_SKILL_NAME]
    if len(v2_installations) > 1:
        issues.append(
            {
                "code": "DUPLICATE_SKILL_NAME",
                "name": V2_SKILL_NAME,
                "paths": [item["path"] for item in v2_installations],
                "hashes": [item["skill_sha256"] for item in v2_installations],
                "message": "Multiple physical V2 installations share the same skill name; no path was modified",
            }
        )

    issue_codes = {str(issue["code"]) for issue in issues}
    if issue_codes & {"SKILL_PATH_ESCAPE", "SKILL_PATH_INVALID", "SKILL_METADATA_INVALID"}:
        status = "PLAN_SKILL_INSTALL_INVALID"
    elif "DUPLICATE_SKILL_NAME" in issue_codes:
        status = "DUPLICATE_SKILL_NAME"
    elif "V1_CANONICAL_MISSING" in issue_codes:
        status = "PLAN_SKILL_V1_MISSING"
    elif "V1_CAPABILITY_NOT_READY" in issue_codes:
        status = "PLAN_SKILL_V1_INCOMPATIBLE"
    elif "V2_CANONICAL_MISSING" in issue_codes:
        status = "PLAN_SKILL_V2_MISSING"
    else:
        status = "PLAN_SKILL_INSTALL_READY"

    return {
        "status": status,
        "skills_root": str(root),
        "canonical": {"v1": str(canonical_v1), "v2": str(canonical_v2)},
        "lesson_tool": lesson_tool,
        "installations": relevant,
        "issues": issues,
    }


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
    parser.add_argument("--check-install-layout", action="store_true", help="Also verify canonical V1/V2 paths and duplicate V2 skill names.")
    parser.add_argument("--skills-root", default=str(default_skills_root()))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        report = check_install_layout(Path(args.skills_root)) if args.check_install_layout else check(Path(args.skill_dir).expanduser())
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        report = {"status": "LESSON_TOOL_UNAVAILABLE", "skill_dir": args.skill_dir, "error": str(exc)}
    code = 0 if report["status"] in {"LESSON_TOOL_READY", "PLAN_SKILL_INSTALL_READY"} else 1
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["status"])
        for error in report.get("errors", []):
            print(f"- {error}", file=sys.stderr)
        for issue in report.get("issues", []):
            print(f"- {issue['code']}: {issue['message']}", file=sys.stderr)
        if report.get("error"):
            print(f"- {report['error']}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
