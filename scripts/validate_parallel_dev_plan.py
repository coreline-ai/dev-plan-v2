#!/usr/bin/env python3
"""Validate a parallel plan JSON source and its rendered Markdown view."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from parallel_plan_lib import load_json, render_plan, validate_plan

PLAN_NAME = re.compile(r"parallel_\d{8}_\d{6}$")


def validate_pair(input_path: Path) -> tuple[Path, Path, list[str]]:
    if input_path.suffix not in {".json", ".md"}:
        return input_path, input_path, ["plan path must end in .json or .md"]
    json_path = input_path.with_suffix(".json")
    markdown_path = input_path.with_suffix(".md")
    errors: list[str] = []
    if not PLAN_NAME.fullmatch(json_path.stem):
        errors.append("plan filename must use parallel_YYYYMMDD_HHMMSS")
    if not json_path.is_file():
        errors.append(f"plan JSON is missing: {json_path}")
        return json_path, markdown_path, errors
    try:
        plan = load_json(json_path)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(str(exc))
        return json_path, markdown_path, errors
    errors.extend(validate_plan(plan))
    if isinstance(plan, dict):
        if plan.get("plan_id") != json_path.stem:
            errors.append("plan_id must match the filename stem")
        if not markdown_path.is_file():
            errors.append(f"rendered Markdown is missing: {markdown_path}")
        else:
            try:
                actual = markdown_path.read_text(encoding="utf-8")
                expected = render_plan(plan, markdown_path.name)
                if actual != expected:
                    errors.append("rendered Markdown does not match the JSON source")
            except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
                errors.append(f"cannot render plan Markdown: {exc}")
    return json_path, markdown_path, list(dict.fromkeys(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="병렬 개발 계획 JSON 정본과 Markdown 표현을 검증합니다.")
    parser.add_argument("plan")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    path = Path(args.plan).expanduser().resolve()
    json_path, markdown_path, errors = validate_pair(path)
    report = {
        "valid": not errors,
        "status": "PARALLEL_PLAN_VALID" if not errors else "PARALLEL_PLAN_INVALID",
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "errors": errors,
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif errors:
        print("PARALLEL_PLAN_INVALID", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print("PARALLEL_PLAN_VALID")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
