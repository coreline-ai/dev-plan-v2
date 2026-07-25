#!/usr/bin/env python3
"""Validate the essential Markdown plan structure without a workflow runtime."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_TOP = (
    "개발 목적", "개발 범위", "제외 범위", "참조 문서", "공통 진행 규칙",
    "실행 상태 및 모델 라우팅", "Phase 상태 요약", "QA 관점", "실행 기록",
)
PHASE = re.compile(r"^## Phase ([1-9][0-9]*)\.\s+(.+)$", re.MULTILINE)
CHECKBOX = re.compile(r"^- \[[ xX]\]\s+\S+", re.MULTILINE)
STATE = re.compile(r"^- 계획 상태: (DRAFT|READY|IN_PROGRESS|BLOCKED|DONE)$", re.MULTILINE)
PLACEHOLDERS = ("확인 필요", "정의 필요", "미배정", "미실행", "TODO", "TBD")
PHASE_SECTIONS = ("목표", "구현 태스크", "자체 테스트", "이슈 및 수정", "완료 조건")


def phase_ranges(text: str, matches: list[re.Match[str]]) -> list[str]:
    return [text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)] for index, match in enumerate(matches)]


def validate(path: Path, *, ready: bool) -> list[str]:
    errors: list[str] = []
    if not re.fullmatch(r"implement_\d{8}_\d{6}\.md", path.name):
        return ["계획 파일은 implement_YYYYMMDD_HHMMSS.md 형식이어야 합니다."]
    text = path.read_text(encoding="utf-8")
    if not text.startswith(f"# {path.name}\n"):
        errors.append("첫 H1은 파일명과 정확히 같아야 합니다.")
    if not re.search(r"^작성 일시: `.+`$", text, re.MULTILINE):
        errors.append("작성 일시가 필요합니다.")
    errors.extend(f"필수 섹션이 없습니다: {heading}" for heading in REQUIRED_TOP if f"## {heading}" not in text)
    matches = list(PHASE.finditer(text))
    if not matches:
        errors.append("최소 한 개의 '## Phase N. 이름' 섹션이 필요합니다.")
    summary = re.findall(r"^- \[[ xX]\] Phase ([1-9][0-9]*) 완료", text, re.MULTILINE)
    if matches and [str(index) for index in range(1, len(matches) + 1)] != summary:
        errors.append("Phase 상태 요약은 모든 Phase와 순서가 같아야 합니다.")
    for index, body in enumerate(phase_ranges(text, matches), start=1):
        for section in PHASE_SECTIONS:
            if f"### {section}" not in body:
                errors.append(f"Phase {index}에 '{section}' 섹션이 없습니다.")
        if not CHECKBOX.search(body):
            errors.append(f"Phase {index}에는 체크리스트가 필요합니다.")
    if not STATE.search(text):
        errors.append("실행 상태는 DRAFT, READY, IN_PROGRESS, BLOCKED, DONE 중 하나여야 합니다.")
    for role in ("Lead:", "ROUTINE Worker:", "COMPLEX Worker:", "Independent QA:"):
        if role not in text:
            errors.append(f"모델 라우팅 항목이 없습니다: {role}")
    if ready:
        if not re.search(r"^- 계획 상태: READY$", text, re.MULTILINE):
            errors.append("실행 전 검증에는 계획 상태 READY가 필요합니다.")
        for token in PLACEHOLDERS:
            if token in text:
                errors.append(f"READY 계획에는 placeholder가 남아 있으면 안 됩니다: {token}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="필수 규약 개발 계획 Markdown을 검사합니다.")
    parser.add_argument("plan")
    parser.add_argument("--ready", action="store_true", help="실행 전 READY 수준의 완결성도 검사")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)
    path = Path(args.plan).expanduser().resolve()
    try:
        errors = validate(path, ready=args.ready)
    except (OSError, UnicodeError) as exc:
        errors = [str(exc)]
    report = {"valid": not errors, "status": "PLAN_VALID" if not errors else "PLAN_INVALID", "ready_check": args.ready, "plan": str(path), "errors": errors}
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
