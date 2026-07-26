#!/usr/bin/env python3
"""Validate the deterministic structure of a parallel development master plan.

This script validates Markdown facts only. It never asserts native model availability,
delegation success, host metadata, or a QA verdict.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REQUIRED_TOP = (
    "개발 목적", "개발 범위", "제외 범위", "참조 문서", "공통 진행 규칙",
    "Workstream 맵", "직렬 scope unit", "병렬 실행 Wave", "Phase 상태 요약", "QA 관점",
)
PHASE = re.compile(r"^## Phase ([1-9][0-9]*)\.\s+(.+)$", re.MULTILINE)
WAVE = re.compile(r"^- Wave ([0-9]+):\s*(.+)$", re.MULTILINE)
CHECKBOX = re.compile(r"^- \[[ xX]\]\s+\S+", re.MULTILINE)
WORKSTREAM_ID = re.compile(r"WS-(?:0*[1-9][0-9]*)$")
FORBIDDEN_PATH_TOKENS = set("*?[]{}")
PHASE_SECTIONS = ("목표", "구현 태스크", "자체 테스트", "이슈 및 수정", "완료 조건")


@dataclass(frozen=True)
class Unit:
    unit_id: str
    allow: tuple[str, ...]
    exclude: tuple[str, ...]
    depends_on: tuple[str, ...]
    kind: str


def split_cells(line: str) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError("Markdown 표 행이 아닙니다.")
    return [cell.strip() for cell in line[1:-1].split("|")]


def items(cell: str) -> tuple[str, ...]:
    if cell.strip() in {"", "-"}:
        return ()
    raw = re.sub(r"`([^`]*)`", r"\1", cell).replace("&#124;", "|")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def normalise_path(path: str) -> str | None:
    value = path.strip()
    if not value or value.startswith("/") or value.startswith("~") or "\\" in value:
        return None
    if ".." in value.split("/") or any(token in value for token in FORBIDDEN_PATH_TOKENS):
        return None
    return value


def overlaps(left: str, right: str) -> bool:
    return left == right or (left.endswith("/") and right.startswith(left)) or (right.endswith("/") and left.startswith(right))


def section_body(text: str, heading: str) -> str | None:
    found = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    if not found:
        return None
    next_heading = re.search(r"^## (?!#)", text[found.end():], re.MULTILINE)
    end = found.end() + next_heading.start() if next_heading else len(text)
    return text[found.end():end]


def read_table(text: str, heading: str, kind: str, errors: list[str]) -> list[Unit]:
    body = section_body(text, heading)
    if body is None:
        return []
    lines = [line for line in body.splitlines() if line.strip()]
    if len(lines) < 3:
        errors.append(f"{heading} 표가 비어 있습니다.")
        return []
    try:
        header, divider = split_cells(lines[0]), split_cells(lines[1])
    except ValueError:
        errors.append(f"{heading} 표 형식이 올바르지 않습니다.")
        return []
    if header != ["ID", "목표", "허용 경로", "제외 경로", "선행 조건", "테스트"] or len(divider) != 6:
        errors.append(f"{heading} 표 헤더가 표준 형식과 다릅니다.")
        return []
    result: list[Unit] = []
    for row_number, line in enumerate(lines[2:], start=3):
        try:
            row = split_cells(line)
        except ValueError:
            errors.append(f"{heading} 표 {row_number}행 형식이 올바르지 않습니다.")
            continue
        if len(row) != 6:
            errors.append(f"{heading} 표 {row_number}행 열 수가 올바르지 않습니다.")
            continue
        unit_id = row[0]
        if not unit_id or not row[1] or not row[2] or not row[5]:
            errors.append(f"{heading} 표 {row_number}행에 ID·목표·허용 경로·테스트가 필요합니다.")
            continue
        allow, exclude, depends_on = items(row[2]), items(row[3]), items(row[4])
        result.append(Unit(unit_id, allow, exclude, depends_on, kind))
    return result


def phase_bodies(text: str, matches: list[re.Match[str]]) -> list[str]:
    return [text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)] for index, match in enumerate(matches)]


def parse_waves(text: str, errors: list[str]) -> dict[int, list[str]]:
    body = section_body(text, "병렬 실행 Wave")
    if body is None:
        return {}
    result: dict[int, list[str]] = {}
    for number_text, names in WAVE.findall(body):
        number = int(number_text)
        unit_ids = [item.strip() for item in names.split(",") if item.strip()]
        if not unit_ids:
            errors.append(f"Wave {number}에 scope unit이 없습니다.")
        elif number in result:
            errors.append(f"Wave {number}가 중복됩니다.")
        else:
            result[number] = unit_ids
    if not result:
        errors.append("병렬 실행 Wave가 하나 이상 필요합니다.")
    return result


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    if not re.fullmatch(r"parallel_\d{8}_\d{6}\.md", path.name):
        return ["계획 파일은 parallel_YYYYMMDD_HHMMSS.md 형식이어야 합니다."]
    text = path.read_text(encoding="utf-8")
    if not text.startswith(f"# {path.name}\n"):
        errors.append("첫 H1은 파일명과 정확히 같아야 합니다.")
    if not re.search(r"^작성 일시: `.+`$", text, re.MULTILINE):
        errors.append("작성 일시가 필요합니다.")
    errors.extend(f"필수 섹션이 없습니다: {heading}" for heading in REQUIRED_TOP if f"## {heading}" not in text)

    matches = list(PHASE.finditer(text))
    if not matches:
        errors.append("최소 한 개의 '## Phase N. 이름' 섹션이 필요합니다.")
    summary = re.findall(r"^- \[[ xX]\] Phase ([1-9][0-9]*) 완료", section_body(text, "Phase 상태 요약") or "", re.MULTILINE)
    if matches and summary != [str(index) for index in range(1, len(matches) + 1)]:
        errors.append("Phase 상태 요약은 모든 Phase와 순서가 같아야 합니다.")
    for index, body in enumerate(phase_bodies(text, matches), start=1):
        for heading in PHASE_SECTIONS:
            if f"### {heading}" not in body:
                errors.append(f"Phase {index}에 '{heading}' 섹션이 없습니다.")
        if not CHECKBOX.search(body):
            errors.append(f"Phase {index}에는 체크리스트가 필요합니다.")

    workstreams = read_table(text, "Workstream 맵", "workstream", errors)
    serial = read_table(text, "직렬 scope unit", "serial", errors)
    if len(workstreams) < 2:
        errors.append("독립 Workstream이 최소 두 개 필요합니다.")
    if any(not WORKSTREAM_ID.fullmatch(unit.unit_id) for unit in workstreams):
        errors.append("Workstream ID는 WS-01 같은 형식이어야 합니다.")
    ids = [unit.unit_id for unit in workstreams + serial]
    if len(ids) != len(set(ids)):
        errors.append("scope unit ID가 중복됩니다.")
    if "INTEGRATION" not in ids:
        errors.append("직렬 scope unit에 INTEGRATION이 필요합니다.")
    if any(unit.unit_id not in {"COMMON", "INTEGRATION"} for unit in serial):
        errors.append("직렬 scope unit은 COMMON 또는 INTEGRATION만 사용할 수 있습니다.")

    for unit in workstreams + serial:
        if not unit.allow:
            errors.append(f"{unit.unit_id}에는 허용 경로가 필요합니다.")
        for path in unit.allow + unit.exclude:
            if normalise_path(path) is None:
                errors.append(f"{unit.unit_id} 경로는 상대 경로이며 glob·상위 경로가 아니어야 합니다: {path}")
        for blocked in unit.exclude:
            if any(overlaps(blocked, allowed) for allowed in unit.allow):
                errors.append(f"{unit.unit_id} 제외 경로가 허용 경로와 겹칩니다: {blocked}")
    units = workstreams + serial
    for index, left in enumerate(units):
        for right in units[index + 1:]:
            for left_path in left.allow:
                for right_path in right.allow:
                    if overlaps(left_path, right_path):
                        errors.append(f"scope unit 허용 경로가 겹칩니다: {left.unit_id}:{left_path} / {right.unit_id}:{right_path}")

    known_ids = set(ids)
    for unit in units:
        for dependency in unit.depends_on:
            if dependency not in known_ids or dependency == unit.unit_id or dependency == "INTEGRATION":
                errors.append(f"{unit.unit_id}의 선행 조건이 유효하지 않습니다: {dependency}")
        if unit.unit_id == "COMMON" and unit.depends_on:
            errors.append("COMMON은 선행 조건을 가질 수 없습니다.")

    waves = parse_waves(text, errors)
    if waves:
        declared = [name for names in waves.values() for name in names]
        if len(declared) != len(set(declared)):
            errors.append("각 계획상 scope unit은 정확히 하나의 Wave에 속해야 합니다.")
        if set(declared) != known_ids:
            errors.append("모든 계획상 scope unit은 정확히 하나의 Wave에 배정되어야 합니다.")
        if "COMMON" in known_ids and waves.get(0) != ["COMMON"]:
            errors.append("COMMON은 Wave 0에만 단독 배정되어야 합니다.")
        if "COMMON" not in known_ids and 0 in waves:
            errors.append("COMMON이 없으면 Wave 0을 만들 수 없습니다.")
        workstream_waves = [number for number, names in waves.items() if any(name in {unit.unit_id for unit in workstreams} for name in names)]
        if any(number < 1 for number in workstream_waves):
            errors.append("Workstream은 Wave 1 이상에 배정되어야 합니다.")
        if "INTEGRATION" in known_ids:
            integration_waves = [number for number, names in waves.items() if "INTEGRATION" in names]
            if len(integration_waves) != 1 or integration_waves[0] != max(waves) or waves[integration_waves[0]] != ["INTEGRATION"]:
                errors.append("INTEGRATION은 마지막 Wave에만 단독 배정되어야 합니다.")
        unit_wave = {unit_id: number for number, names in waves.items() for unit_id in names}
        for unit in units:
            for dependency in unit.depends_on:
                if dependency in unit_wave and unit.unit_id in unit_wave and unit_wave[dependency] >= unit_wave[unit.unit_id]:
                    errors.append(f"{unit.unit_id}의 선행 조건 {dependency}는 더 이른 Wave에 있어야 합니다.")
    return errors


def main(argv: list[str] | None = None) -> int:
    command = argparse.ArgumentParser(description="병렬 개발 master 계획 Markdown 구조를 검사합니다.")
    command.add_argument("plan")
    command.add_argument("--format", choices=("text", "json"), default="text")
    args = command.parse_args(argv)
    path = Path(args.plan).expanduser().resolve()
    try:
        errors = validate(path)
    except (OSError, UnicodeError) as exc:
        errors = [str(exc)]
    report = {"valid": not errors, "status": "PARALLEL_PLAN_VALID" if not errors else "PARALLEL_PLAN_INVALID", "plan": str(path), "errors": errors}
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
