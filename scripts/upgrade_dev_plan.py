#!/usr/bin/env python3
"""Conservatively upgrade a legacy development plan into a new v2 DRAFT."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
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
        validate_structural,
    )
except ImportError:
    from plan_core import (  # type: ignore
        PlanError,
        build_plan_content,
        now_iso,
        parse_plan,
        validate_structural,
    )


SKIP_H2 = {
    "개발 목적",
    "개발 범위",
    "제외 범위",
    "참조 문서",
    "공통 진행 규칙",
    "Phase 상태 요약",
    "QA 관점",
    "최종 통합 QA",
    "최종 승인",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="기존 개발 계획을 보존하며 v2 DRAFT로 업그레이드합니다.")
    parser.add_argument("source", help="원본 v1 Markdown 계획")
    parser.add_argument("--root", default=".", help="대상 프로젝트 루트")
    parser.add_argument("--output-dir", help="저장 폴더 (기본값: <root>/dev-plan)")
    parser.add_argument("--lead-model", default="gpt-5.6-sol")
    parser.add_argument("--qa-model", default="gpt-5.6-sol")
    parser.add_argument(
        "--isolation-mode",
        choices=["CAPABILITY", "MANIFEST_GUARDED"],
        default="MANIFEST_GUARDED",
    )
    parser.add_argument("--timestamp", help="파일명용 YYYYMMDD_HHMMSS")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _section(lines: list[str], title: str) -> list[str]:
    start = next(
        (index for index, line in enumerate(lines) if re.match(rf"^##\s+{re.escape(title)}\s*$", line)),
        None,
    )
    if start is None:
        return []
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return [line.strip("- ").strip() for line in lines[start + 1 : end] if line.strip() and not line.startswith("#")]


def _legacy_phases(lines: list[str]) -> list[dict[str, Any]]:
    phase_starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^##\s+(?:Phase\s*[0-9]+[.:]?\s*)?(.+?)\s*$", line)
        if not match:
            continue
        title = match.group(1).strip()
        if title in SKIP_H2:
            continue
        if "Phase" in line or re.match(r"^[0-9]+[.)]\s+", title):
            phase_starts.append((index, re.sub(r"^[0-9]+[.)]\s*", "", title)))
    if not phase_starts:
        phase_starts = [(0, "Legacy 계획 변환")]

    phases: list[dict[str, Any]] = []
    for phase_index, (start, name) in enumerate(phase_starts):
        end = phase_starts[phase_index + 1][0] if phase_index + 1 < len(phase_starts) else len(lines)
        segment = lines[start:end]
        heading_titles: list[str] = []
        checkbox_titles: list[str] = []
        for line in segment:
            heading = re.match(r"^#{3,4}\s+(?:DEV-[0-9]+\s+)?(.+?)\s*$", line)
            checkbox = re.match(r"^-\s+\[[ xX]\]\s+(.+?)\s*$", line)
            for match, target in ((heading, heading_titles), (checkbox, checkbox_titles)):
                title = match.group(1).strip() if match else ""
                if not title or any(word in title for word in ("완료 조건", "자체 테스트", "독립 QA", "모든 Phase")):
                    continue
                if title not in target:
                    target.append(title)
        task_titles = heading_titles or checkbox_titles
        if not task_titles:
            task_titles = ["TODO 원본 Phase 구현 태스크를 식별한다."]
        tasks = [
            {
                "title": title,
                "objective": f"TODO 원본의 '{title}' 목표와 변경 범위를 확인한다.",
                "allowed_paths": ["TODO"],
                "allowed_new_paths": ["TODO"],
                "read_paths": ["TODO"],
                "dependencies": [],
                "complexity": "ROUTINE",
                "acceptance_criteria": ["TODO 원본 완료 조건을 재현 가능한 기준으로 변환한다."],
                "tests": [
                    {
                        "title": f"{title} 검증",
                        "kind": "manual",
                        "steps": ["TODO 원본 검증 절차를 재현 가능한 단계로 변환한다."],
                        "expected": "TODO 기대 결과를 구체화한다.",
                        "evidence_required": ["TODO 실행 로그 또는 재현 증빙"],
                    }
                ],
            }
            for title in task_titles
        ]
        phases.append(
            {
                "name": name or f"Legacy Phase {phase_index + 1}",
                "goal": f"TODO 원본 Phase '{name}'의 목표를 확인한다.",
                "tasks": tasks,
            }
        )
    return phases


def legacy_spec(source: Path, raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8")
    lines = text.splitlines()
    source_digest = sha256_bytes(raw)
    purpose_lines = _section(lines, "개발 목적")
    scope_lines = _section(lines, "개발 범위")
    exclude_lines = _section(lines, "제외 범위")
    source_ref = {
        "path": str(source),
        "sha256": source_digest,
        "bytes": len(raw),
    }
    return {
        "purpose": purpose_lines[0] if purpose_lines else "TODO 원본 계획의 개발 목적을 확인한다.",
        "scope": scope_lines or ["TODO 원본 계획의 개발 범위를 확인한다."],
        "excludes": exclude_lines or ["TODO 원본 계획의 제외 범위를 확인한다."],
        "references": [
            f"업그레이드 원본: `{source}`",
            f"업그레이드 원본 SHA-256: `{source_digest}`",
        ],
        "upgrade_source": source_ref,
        "phases": _legacy_phases(lines),
    }


def upgrade(args: argparse.Namespace) -> tuple[Path, dict[str, Any], list[str]]:
    source = Path(args.source).expanduser().resolve()
    raw = source.read_bytes()
    if not source.is_file():
        raise PlanError("SOURCE_INVALID", f"Source is not a file: {source}")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanError("SOURCE_ENCODING", "Source plan must be UTF-8") from exc

    root = Path(args.root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "dev-plan"
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
    content = build_plan_content(
        filename=filename,
        plan_id=f"PLAN-{stamp.replace('_', '-')}",
        created_at=created_at,
        spec=legacy_spec(source, raw),
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
        structural = validate_structural(doc)
        if structural:
            raise structural[0]
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    missing = sorted(
        {
            line.strip()
            for line in destination.read_text(encoding="utf-8").splitlines()
            if "TODO" in line or "UNSET" in line
        }
    )
    return destination, doc.metadata, missing


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        path, metadata, missing = upgrade(args)
    except (PlanError, OSError, ValueError) as exc:
        error = exc.as_dict() if isinstance(exc, PlanError) else {"code": "INTERNAL_ERROR", "message": str(exc)}
        if args.format == "json":
            print(json.dumps({"status": "UPGRADE_FAILED", "error": error}, ensure_ascii=False, indent=2))
        else:
            print(f"UPGRADE_FAILED [{error['code']}]: {error['message']}", file=sys.stderr)
        return 2
    report = {
        "status": "PLAN_UPGRADED_DRAFT",
        "path": str(path),
        "plan_id": metadata["plan_id"],
        "plan_status": metadata["status"],
        "missing_count": len(missing),
        "missing": missing,
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("PLAN_UPGRADED_DRAFT")
        print(f"path: {path}")
        print(f"plan_id: {metadata['plan_id']}")
        print(f"missing_count: {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
