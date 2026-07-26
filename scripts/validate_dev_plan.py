#!/usr/bin/env python3
"""Validate a phased Markdown plan and its fail-closed model-routing records."""

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
PHASE_SECTIONS = ("목표", "Worker 배정", "구현 태스크", "자체 테스트", "이슈 및 수정", "완료 조건")
PLACEHOLDERS = ("확인 필요", "정의 필요", "TODO", "TBD")


def phase_ranges(text: str, matches: list[re.Match[str]]) -> list[str]:
    return [text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)] for index, match in enumerate(matches)]


def line_value(text: str, label: str) -> str | None:
    match = re.search(rf"^- {re.escape(label)}: (.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def model_has(value: str | None, role: str) -> bool:
    if value is None or value in {"UNASSIGNED", "PENDING", "UNVERIFIED", "NOT_REPORTED"}:
        return False
    return re.search(rf"(?:^|[-_/;,\s]){re.escape(role)}(?:$|[-_/;,\s])", value, re.IGNORECASE) is not None


def runtime_lists(runtime: str | None, model: str | None) -> bool:
    """Return true only when the exact requested id is in the recorded runtime list."""
    if runtime is None or model is None:
        return False
    listed = {item.strip() for item in re.split(r"[,;]", runtime) if item.strip()}
    return model in listed


def require_exact(value: str | None, expected: str, field: str, errors: list[str]) -> None:
    if value != expected:
        errors.append(f"{field}은(는) '{expected}'이어야 합니다.")


def require_actual_match(
    text: str, requested_label: str, actual_label: str, subject: str, errors: list[str]
) -> None:
    requested = line_value(text, requested_label)
    actual = line_value(text, actual_label)
    if actual != requested:
        errors.append(f"{subject} actual model은 requested model과 정확히 같아야 합니다.")


def validate_structure(path: Path) -> tuple[str, list[re.Match[str]], list[str]]:
    errors: list[str] = []
    if not re.fullmatch(r"implement_\d{8}_\d{6}\.md", path.name):
        return "", [], ["계획 파일은 implement_YYYYMMDD_HHMMSS.md 형식이어야 합니다."]
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
        tier = line_value(body, "작업 등급")
        if tier not in {"ROUTINE", "COMPLEX"}:
            errors.append(f"Phase {index} Worker 작업 등급은 ROUTINE 또는 COMPLEX여야 합니다.")
    if not STATE.search(text):
        errors.append("실행 상태는 DRAFT, READY, IN_PROGRESS, BLOCKED, DONE 중 하나여야 합니다.")
    for field in (
        "확인된 런타임 모델", "Lead requested model", "Lead actual model", "Lead context",
        "QA requested model", "QA actual model", "QA context", "QA verdict",
    ):
        if line_value(text, field) is None:
            errors.append(f"모델 라우팅 항목이 없습니다: {field}")
    return text, matches, errors


def validate_routing(text: str, matches: list[re.Match[str]], errors: list[str]) -> None:
    runtime = line_value(text, "확인된 런타임 모델")
    if runtime in {None, "UNVERIFIED", ""}:
        errors.append("READY 계획은 실제 확인된 런타임 모델 목록을 기록해야 합니다.")
    if not model_has(runtime, "sol"):
        errors.append("READY 계획에는 실제 지원되는 Sol 모델이 필요합니다.")
    if not model_has(line_value(text, "Lead requested model"), "sol"):
        errors.append("Lead requested model은 실제 Sol 모델이어야 합니다.")
    elif not runtime_lists(runtime, line_value(text, "Lead requested model")):
        errors.append("Lead requested model은 확인된 런타임 모델 목록에 정확히 있어야 합니다.")
    require_exact(line_value(text, "Lead context"), "fork_turns: none", "Lead context", errors)
    if not model_has(line_value(text, "QA requested model"), "sol"):
        errors.append("QA requested model은 실제 새 Sol 모델이어야 합니다.")
    elif not runtime_lists(runtime, line_value(text, "QA requested model")):
        errors.append("QA requested model은 확인된 런타임 모델 목록에 정확히 있어야 합니다.")
    require_exact(line_value(text, "QA context"), "fork_turns: none", "QA context", errors)
    for index, body in enumerate(phase_ranges(text, matches), start=1):
        tier = line_value(body, "작업 등급")
        requested = line_value(body, "requested model")
        expected = "luna" if tier == "COMPLEX" else "terra"
        if not model_has(requested, expected):
            errors.append(f"Phase {index} requested model은 실제 {expected.title()} 모델이어야 합니다.")
        elif not runtime_lists(runtime, requested):
            errors.append(f"Phase {index} requested model은 확인된 런타임 모델 목록에 정확히 있어야 합니다.")
        require_exact(line_value(body, "context"), "fork_turns: none", f"Phase {index} Worker context", errors)
        if tier == "COMPLEX" and not model_has(runtime, "luna"):
            errors.append(f"Phase {index}은 COMPLEX지만 실제 Luna 모델이 없습니다. BLOCKED 또는 재분해가 필요합니다.")
    for token in PLACEHOLDERS:
        if token in text:
            errors.append(f"모델 배정 완료 계획에는 placeholder가 남아 있으면 안 됩니다: {token}")


def validate_ready(text: str, matches: list[re.Match[str]], errors: list[str]) -> None:
    require_exact(line_value(text, "계획 상태"), "READY", "계획 상태", errors)
    validate_routing(text, matches, errors)


def validate_complete(text: str, matches: list[re.Match[str]], errors: list[str]) -> None:
    require_exact(line_value(text, "계획 상태"), "DONE", "계획 상태", errors)
    validate_routing(text, matches, errors)
    for role in ("Lead", "QA"):
        if not model_has(line_value(text, f"{role} actual model"), "sol"):
            errors.append(f"완료 계획의 {role} actual model은 host가 반환한 Sol 모델이어야 합니다.")
        require_actual_match(text, f"{role} requested model", f"{role} actual model", role, errors)
    if line_value(text, "QA verdict") != "PASS":
        errors.append("완료 계획에는 QA verdict PASS가 필요합니다.")
    if "- 실행한 테스트: 미실행" in text or "- Worker 보고: 미실행" in text:
        errors.append("완료 계획에는 실제 테스트와 Worker 보고가 필요합니다.")
    if re.search(r"^- \[ \] Phase [1-9][0-9]* 완료", text, re.MULTILINE):
        errors.append("완료 계획의 모든 Phase 상태 요약은 완료여야 합니다.")
    for index, body in enumerate(phase_ranges(text, matches), start=1):
        expected = "luna" if line_value(body, "작업 등급") == "COMPLEX" else "terra"
        if not model_has(line_value(body, "actual model"), expected):
            errors.append(f"완료 계획의 Phase {index} actual model은 host가 반환한 {expected.title()} 모델이어야 합니다.")
        require_actual_match(body, "requested model", "actual model", f"Phase {index} Worker", errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="모델 라우팅이 포함된 개발 계획 Markdown을 검사합니다.")
    parser.add_argument("plan")
    parser.add_argument("--ready", action="store_true", help="실행 전 모델 preflight와 배정도 검사")
    parser.add_argument("--complete", action="store_true", help="완료 모델/테스트/QA 기록도 검사")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)
    if args.ready and args.complete:
        parser.error("--ready and --complete cannot be used together")
    path = Path(args.plan).expanduser().resolve()
    try:
        text, matches, errors = validate_structure(path)
        if not errors and args.ready:
            validate_ready(text, matches, errors)
        if not errors and args.complete:
            validate_complete(text, matches, errors)
    except (OSError, UnicodeError) as exc:
        errors = [str(exc)]
    report = {"valid": not errors, "status": "PLAN_VALID" if not errors else "PLAN_INVALID", "ready_check": args.ready, "complete_check": args.complete, "plan": str(path), "errors": errors}
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
