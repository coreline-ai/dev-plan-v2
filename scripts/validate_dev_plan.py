#!/usr/bin/env python3
"""Validate the intentionally small Markdown plan format."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_HEADINGS = ("개발 목적", "범위", "제외 범위", "참조", "실행 규칙", "QA 체크리스트", "실행 기록")
PHASE = re.compile(r"^## Phase [1-9][0-9]*\.\s+\S+", re.MULTILINE)
CHECKBOX = re.compile(r"^- \[[ xX]\]\s+\S+", re.MULTILINE)


def validate(path: Path) -> list[str]:
    if path.name.startswith("implement_") is False or path.suffix != ".md":
        return ["계획 파일은 implement_*.md 형식이어야 합니다."]
    text = path.read_text(encoding="utf-8")
    errors = [f"필수 섹션이 없습니다: {heading}" for heading in REQUIRED_HEADINGS if f"## {heading}" not in text]
    if not PHASE.search(text):
        errors.append("최소 한 개의 '## Phase N. 이름' 섹션이 필요합니다.")
    if not CHECKBOX.search(text):
        errors.append("최소 한 개의 체크리스트 항목이 필요합니다.")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="간단한 개발 계획 Markdown을 검사합니다.")
    parser.add_argument("plan")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)
    try:
        path = Path(args.plan).expanduser().resolve()
        errors = validate(path)
    except (OSError, UnicodeError) as exc:
        errors = [str(exc)]
    report = {"valid": not errors, "status": "PLAN_VALID" if not errors else "PLAN_INVALID", "plan": str(path), "errors": errors}
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif errors:
        print("PLAN_INVALID", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print("PLAN_VALID")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
