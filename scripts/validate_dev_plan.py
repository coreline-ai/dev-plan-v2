#!/usr/bin/env python3
"""Validate structural or executable invariants of a v2 development plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import markdown_it  # noqa: F401
    import yaml  # noqa: F401
except ModuleNotFoundError as exc:
    print(
        f"RUNTIME_DEPENDENCY_MISSING: {exc.name}. Run scripts/check_runtime.py for the "
        "isolated-environment installation command.",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

try:
    from .plan_core import (
        PlanError,
        load_yaml,
        make_error_report,
        parse_plan,
        validate_executable,
        validate_structural,
    )
except ImportError:
    from plan_core import (  # type: ignore
        PlanError,
        load_yaml,
        make_error_report,
        parse_plan,
        validate_executable,
        validate_structural,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="codex-dev-plan/v2 계획을 검증합니다.")
    parser.add_argument("plan", help="검증할 implement_*.md")
    parser.add_argument("--level", choices=["structural", "executable"], default="structural")
    parser.add_argument("--target-state", choices=["READY", "IN_PROGRESS", "QA"])
    parser.add_argument("--candidate-event", help="아직 적용하지 않은 YAML/JSON 이벤트")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--skip-evidence-check",
        action="store_true",
        help="구조만 재현하는 제한적 진단용; 상태 적용에는 사용할 수 없음",
    )
    return parser


def read_event(path: str) -> dict[str, Any]:
    event_path = Path(path).expanduser()
    text = event_path.read_text(encoding="utf-8")
    if event_path.suffix.lower() == ".json":
        value = json.loads(text)
    else:
        value = load_yaml(text, source=str(event_path))
    if not isinstance(value, dict):
        raise PlanError("EVENT_PAYLOAD_INVALID", "Candidate event must be a mapping")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        doc = parse_plan(args.plan)
        event = read_event(args.candidate_event) if args.candidate_event else None
        if args.level == "structural":
            if event or args.target_state:
                parser.error("--candidate-event and --target-state require --level executable")
            errors = validate_structural(doc)
        else:
            errors = validate_executable(
                doc,
                target_state=args.target_state,
                candidate_event=event,
                check_evidence=not args.skip_evidence_check,
            )
        report = make_error_report(errors, executable=args.level == "executable")
        report.update(
            {
                "level": args.level,
                "plan": str(doc.path),
                "plan_id": doc.metadata.get("plan_id"),
                "plan_status": args.target_state or doc.metadata.get("status"),
                "source_plan_status": doc.metadata.get("status"),
            }
        )
    except SystemExit:
        raise
    except (PlanError, OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "valid": False,
            "status": "VALIDATOR_ERROR",
            "level": args.level,
            "errors": [exc.as_dict() if isinstance(exc, PlanError) else {"code": "INTERNAL_ERROR", "message": str(exc)}],
        }
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"VALIDATOR_ERROR: {report['errors'][0]['message']}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["valid"]:
        print("PLAN_VALID")
        print(f"level: {args.level}")
        print(f"plan_id: {report['plan_id']}")
    else:
        print(report["status"])
        for error in report["errors"]:
            entity = f" [{error['entity']}]" if error.get("entity") else ""
            print(f"- {error['code']}{entity}: {error['message']}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
