#!/usr/bin/env python3
"""Build a deterministic, runtime-only skill directory from the repository source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_NAME = "codex-dev-plan-orchestrator"
RUNTIME_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "pyproject.toml",
    "scripts/__init__.py",
    "scripts/plan_core.py",
    "scripts/check_runtime.py",
    "scripts/workspace_guard.py",
    "scripts/new_dev_plan.py",
    "scripts/upgrade_dev_plan.py",
    "scripts/validate_dev_plan.py",
    "scripts/update_plan_state.py",
    "references/plan-schema-v2.md",
    "references/execution-workflow.md",
    "references/agent-contracts.md",
)
DEFAULT_QUICK_VALIDATOR = (
    Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    / "skills"
    / ".system"
    / "skill-creator"
    / "scripts"
    / "quick_validate.py"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="런타임 allowlist만 포함한 스킬 디렉터리를 패키징합니다.")
    parser.add_argument("--source", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--output", default="dist", help="패키지 상위 폴더")
    parser.add_argument("--quick-validator", help="skill-creator quick_validate.py 경로")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_internal_links(root: Path) -> None:
    link_pattern = re.compile(r"\[[^\]]+\]\((?!https?://|#)([^)#]+)(?:#[^)]+)?\)")
    missing: list[str] = []
    for markdown in root.rglob("*.md"):
        text = markdown.read_text(encoding="utf-8")
        for target in link_pattern.findall(text):
            destination = (markdown.parent / target).resolve()
            if not destination.is_relative_to(root.resolve()) or not destination.exists():
                missing.append(f"{markdown.relative_to(root)} -> {target}")
    if missing:
        raise RuntimeError("Broken internal links: " + ", ".join(missing))


def package(args: argparse.Namespace) -> dict[str, object]:
    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    destination = output / SKILL_NAME
    if destination.exists():
        raise FileExistsError(f"Package destination already exists: {destination}")
    missing = [relative for relative in RUNTIME_FILES if not (source / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing runtime files: {', '.join(missing)}")

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{SKILL_NAME}-", dir=output) as temp_dir:
        staging = Path(temp_dir) / SKILL_NAME
        for relative in RUNTIME_FILES:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)

        validate_internal_links(staging)
        validator_path = (
            Path(args.quick_validator).expanduser().resolve()
            if args.quick_validator
            else DEFAULT_QUICK_VALIDATOR
        )
        if not validator_path.is_file():
            raise FileNotFoundError(f"quick_validate.py not found: {validator_path}")
        completed = subprocess.run(
            [sys.executable, str(validator_path), str(staging)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            detail = (completed.stdout + completed.stderr).strip()
            raise RuntimeError(f"quick_validate.py failed: {detail}")
        validator_result = (completed.stdout + completed.stderr).strip() or "PASS"
        staging.rename(destination)

    files = [
        {
            "path": str(path.relative_to(destination)),
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    ]
    manifest = {
        "schema": "codex-skill-package-manifest/v1",
        "skill": SKILL_NAME,
        "validation": validator_result,
        "validator": {
            "id": "skill-creator/scripts/quick_validate.py",
            "sha256": file_sha256(validator_path),
        },
        "files": files,
    }
    manifest_path = output / f"{SKILL_NAME}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        **manifest,
        "source": str(source),
        "destination": str(destination),
        "manifest_path": str(manifest_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = package(args)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if args.format == "json":
            print(json.dumps({"status": "PACKAGE_FAILED", "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"PACKAGE_FAILED: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps({"status": "PACKAGE_CREATED", **result}, ensure_ascii=False, indent=2))
    else:
        print("PACKAGE_CREATED")
        print(f"path: {result['destination']}")
        print(f"files: {len(result['files'])}")
        print(f"validation: {result['validation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
