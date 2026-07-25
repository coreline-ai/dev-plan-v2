#!/usr/bin/env python3
"""Create a new codex-dev-plan/v2 document without overwriting existing plans."""

from __future__ import annotations

import argparse
import datetime as dt
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
        build_plan_content,
        now_iso,
        parse_plan,
        read_spec,
        validate_structural,
    )
except ImportError:
    from plan_core import (  # type: ignore
        PlanError,
        build_plan_content,
        now_iso,
        parse_plan,
        read_spec,
        validate_structural,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="새 codex-dev-plan/v2 DRAFT 계획을 생성합니다.")
    parser.add_argument("--root", default=".", help="대상 프로젝트 루트 (기본값: 현재 폴더)")
    parser.add_argument("--output-dir", help="계획 저장 폴더 (기본값: <root>/dev-plan)")
    parser.add_argument("--spec", help="구조화된 YAML 또는 JSON 계획 입력")
    parser.add_argument("--purpose", help="개발 목적")
    parser.add_argument("--scope", action="append", default=[], help="개발 범위 (반복 가능)")
    parser.add_argument("--exclude", action="append", default=[], help="제외 범위 (반복 가능)")
    parser.add_argument("--reference", action="append", default=[], help="참조 문서 (반복 가능)")
    parser.add_argument("--phase", action="append", default=[], help="Phase 이름 (반복 가능)")
    parser.add_argument("--lead-model", default="gpt-5.6-sol", help="Lead 모델의 실제 런타임 ID")
    parser.add_argument("--qa-model", default="gpt-5.6-sol", help="QA 모델의 실제 런타임 ID")
    parser.add_argument(
        "--isolation-mode",
        choices=["CAPABILITY", "MANIFEST_GUARDED"],
        default="MANIFEST_GUARDED",
    )
    parser.add_argument(
        "--timestamp",
        help="파일명용 YYYYMMDD_HHMMSS (재현 테스트 또는 외부 조정용)",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def spec_from_args(args: argparse.Namespace) -> dict[str, Any]:
    spec = read_spec(args.spec) if args.spec else {}
    if args.purpose:
        spec["purpose"] = args.purpose
    if args.scope:
        spec["scope"] = args.scope
    if args.exclude:
        spec["excludes"] = args.exclude
    if args.reference:
        spec["references"] = args.reference
    if args.phase:
        spec["phases"] = [
            {
                "name": name,
                "goal": f"TODO {name} Phase 목표를 구체화한다.",
                "tasks": [],
            }
            for name in args.phase
        ]
    return spec


def create_plan(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise PlanError("ROOT_INVALID", f"Project root is not a directory: {root}")
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else root / "dev-plan"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.timestamp:
        try:
            stamp_dt = dt.datetime.strptime(args.timestamp, "%Y%m%d_%H%M%S")
        except ValueError as exc:
            raise PlanError("TIMESTAMP_INVALID", "--timestamp must be YYYYMMDD_HHMMSS") from exc
        stamp = stamp_dt.strftime("%Y%m%d_%H%M%S")
        created_at = stamp_dt.astimezone().isoformat(timespec="seconds")
    else:
        stamp = dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        created_at = now_iso()

    filename = f"implement_{stamp}.md"
    destination = output_dir / filename
    plan_id = f"PLAN-{stamp.replace('_', '-')}"
    content = build_plan_content(
        filename=filename,
        plan_id=plan_id,
        created_at=created_at,
        spec=spec_from_args(args),
        lead_model=args.lead_model,
        qa_model=args.qa_model,
        isolation_mode=args.isolation_mode,
    )
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise PlanError("PLAN_COLLISION", f"Plan already exists: {destination}") from exc

    try:
        doc = parse_plan(destination)
        errors = validate_structural(doc)
        if errors:
            raise errors[0]
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination, doc.metadata


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        path, metadata = create_plan(args)
    except (PlanError, OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "status": "PLAN_CREATE_FAILED",
            "error": exc.as_dict() if isinstance(exc, PlanError) else {"message": str(exc)},
        }
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else f"PLAN_CREATE_FAILED: {report['error']['message']}", file=sys.stderr)
        return 2

    report = {
        "status": "PLAN_CREATED",
        "path": str(path),
        "plan_id": metadata["plan_id"],
        "plan_status": metadata["status"],
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("PLAN_CREATED")
        print(f"path: {path}")
        print(f"plan_id: {metadata['plan_id']}")
        print(f"status: {metadata['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
