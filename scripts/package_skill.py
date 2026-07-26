#!/usr/bin/env python3
"""Package only the small runtime skill surface."""

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

SKILL_NAME = "parallel-dev-plan-orchestrator"
RUNTIME_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/new_parallel_dev_plan.py",
    "scripts/validate_parallel_dev_plan.py",
    "scripts/check_parallel_scope.py",
    "references/parallel-plan-format.md",
    "references/parallel-execution-workflow.md",
)
DEFAULT_QUICK_VALIDATOR = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_links(root: Path) -> None:
    links = re.compile(r"\[[^\]]+\]\((?!https?://|#)([^)#]+)(?:#[^)]+)?\)")
    for markdown in root.rglob("*.md"):
        for target in links.findall(markdown.read_text(encoding="utf-8")):
            if not (markdown.parent / target).resolve().is_relative_to(root.resolve()) or not (markdown.parent / target).resolve().exists():
                raise RuntimeError(f"Broken internal link: {markdown.relative_to(root)} -> {target}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="경량 런타임 파일만 패키징합니다.")
    parser.add_argument("--source", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--output", default="dist")
    parser.add_argument("--quick-validator")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)
    try:
        source, output = Path(args.source).expanduser().resolve(), Path(args.output).expanduser().resolve()
        destination = output / SKILL_NAME
        if destination.exists():
            raise FileExistsError(f"Package destination already exists: {destination}")
        missing = [item for item in RUNTIME_FILES if not (source / item).is_file()]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output, prefix=".skill-") as temporary:
            staging = Path(temporary) / SKILL_NAME
            for item in RUNTIME_FILES:
                target = staging / item
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / item, target)
            check_links(staging)
            validator = Path(args.quick_validator).expanduser().resolve() if args.quick_validator else DEFAULT_QUICK_VALIDATOR
            if not validator.is_file():
                raise FileNotFoundError(f"quick_validate.py not found: {validator}")
            checked = subprocess.run([sys.executable, str(validator), str(staging)], capture_output=True, text=True, check=False, timeout=60)
            if checked.returncode:
                raise RuntimeError((checked.stdout + checked.stderr).strip())
            staging.rename(destination)
        files = [{"path": str(item.relative_to(destination)), "sha256": sha256(item), "bytes": item.stat().st_size} for item in sorted(destination.rglob("*")) if item.is_file()]
        manifest = {"schema": "codex-skill-package-manifest/v1", "skill": SKILL_NAME, "files": files}
        manifest_path = output / f"{SKILL_NAME}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = {"status": "PACKAGE_CREATED", **manifest, "destination": str(destination), "manifest_path": str(manifest_path)}
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        report = {"status": "PACKAGE_FAILED", "error": str(exc)}
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"PACKAGE_FAILED: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"PACKAGE_CREATED: {report['destination']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
