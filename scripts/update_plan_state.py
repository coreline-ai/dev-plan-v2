#!/usr/bin/env python3
"""Apply one allowlisted state event with atomic CAS semantics."""

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
        apply_event_atomic,
        load_yaml,
        text_sha256,
    )
except ImportError:
    from plan_core import (  # type: ignore
        PlanError,
        apply_event_atomic,
        load_yaml,
        text_sha256,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lead 전용 v2 계획 상태 갱신기")
    subparsers = parser.add_subparsers(dest="command", required=True)
    apply_parser = subparsers.add_parser("apply-event", help="검증된 상태 이벤트 한 개 적용")
    apply_parser.add_argument("plan", help="대상 implement_*.md")
    apply_parser.add_argument("--event-file", required=True, help="YAML 또는 JSON 이벤트")
    apply_parser.add_argument("--expected-document-sha256", required=True)
    apply_parser.add_argument("--expected-document-version", required=True, type=int)
    apply_parser.add_argument("--dry-run", action="store_true")
    apply_parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def read_event(path: str) -> dict[str, Any]:
    event_path = Path(path).expanduser()
    text = event_path.read_text(encoding="utf-8")
    value = json.loads(text) if event_path.suffix.lower() == ".json" else load_yaml(text, source=str(event_path))
    if not isinstance(value, dict):
        raise PlanError("EVENT_PAYLOAD_INVALID", "Event must be a mapping")
    return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        event = read_event(args.event_file)
        doc, diff = apply_event_atomic(
            args.plan,
            event,
            expected_sha256=args.expected_document_sha256,
            expected_document_version=args.expected_document_version,
            dry_run=args.dry_run,
            verify_evidence=True,
        )
        current_text = doc.render() if args.dry_run else Path(args.plan).expanduser().resolve().read_text(encoding="utf-8")
        report = {
            "status": "EVENT_VALID" if args.dry_run else "EVENT_APPLIED",
            "dry_run": args.dry_run,
            "plan": str(Path(args.plan).expanduser().resolve()),
            "plan_id": doc.metadata.get("plan_id"),
            "plan_status": doc.metadata.get("status"),
            "document_version": doc.metadata.get("document_version"),
            "document_sha256": text_sha256(current_text),
            "diff": diff,
        }
    except (PlanError, OSError, ValueError, json.JSONDecodeError) as exc:
        error = exc.as_dict() if isinstance(exc, PlanError) else {"code": "INTERNAL_ERROR", "message": str(exc)}
        report = {"status": "EVENT_REJECTED", "error": error}
        if getattr(args, "format", "text") == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"EVENT_REJECTED [{error['code']}]: {error['message']}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["status"])
        print(f"plan_id: {report['plan_id']}")
        print(f"status: {report['plan_status']}")
        print(f"document_version: {report['document_version']}")
        print(f"document_sha256: {report['document_sha256']}")
        if diff:
            print(diff, end="" if diff.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
