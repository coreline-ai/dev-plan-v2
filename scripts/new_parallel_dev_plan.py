#!/usr/bin/env python3
"""Create a parallel-only development master plan.

The generator intentionally writes only planning facts. Runtime model availability,
delegation results, and QA results belong to EXECUTE/RESUME, not this file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

WORKSTREAM_ID = re.compile(r"WS-(?:0*[1-9][0-9]*)$")
FORBIDDEN_PATH_TOKENS = set("*?[]{}")


@dataclass(frozen=True)
class Unit:
    unit_id: str
    goal: str
    allow: tuple[str, ...]
    exclude: tuple[str, ...]
    tests: tuple[str, ...]
    depends_on: tuple[str, ...]
    kind: str


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="병렬 개발 master 계획 Markdown을 생성합니다.")
    result.add_argument("--root", default=".", help="대상 프로젝트 루트")
    result.add_argument("--purpose", required=True, help="개발 목적")
    result.add_argument("--scope", action="append", default=[], help="전체 개발 범위 (반복 가능)")
    result.add_argument("--exclude", action="append", default=[], help="전체 제외 범위 (반복 가능)")
    result.add_argument("--reference", action="append", default=[], help="참조 문서/파일 (반복 가능)")
    result.add_argument("--previous-plan", help="참조 문서 첫 항목에 넣을 이전 V1/V2 계획 경로")
    result.add_argument(
        "--workstream",
        action="append",
        default=[],
        metavar="JSON",
        help='반복 가능한 JSON: {"id":"WS-01","goal":"...","allow":["src/a/"],"exclude":[],"tests":["pytest ..."],"depends_on":[]}',
    )
    result.add_argument(
        "--common",
        metavar="JSON",
        help='선택 JSON: {"goal":"...","allow":[...],"exclude":[...],"tests":[...]}',
    )
    result.add_argument(
        "--integration",
        required=True,
        metavar="JSON",
        help='필수 JSON: {"goal":"...","allow":[...],"exclude":[...],"tests":[...]}',
    )
    result.add_argument("--phase", action="append", default=[], help="Phase 이름 (반복 가능)")
    result.add_argument("--timestamp", help="재현용 YYYYMMDD_HHMMSS")
    result.add_argument("--format", choices=("text", "json"), default="text")
    return result


def _text_list(value: object, field: str, unit_id: str, *, required: bool = False) -> tuple[str, ...]:
    if value is None:
        values: list[object] = []
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError(f"{unit_id}.{field}은(는) 문자열 목록이어야 합니다.")
    cleaned: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{unit_id}.{field}에는 비어 있지 않은 문자열만 넣을 수 있습니다.")
        cleaned.append(item.strip())
    if required and not cleaned:
        raise ValueError(f"{unit_id}.{field}은(는) 하나 이상 필요합니다.")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{unit_id}.{field}에 중복 값이 있습니다.")
    return tuple(cleaned)


def normalise_path(path: str, unit_id: str, field: str) -> str:
    value = path.strip()
    if not value or value.startswith("/") or value.startswith("~") or "\\" in value:
        raise ValueError(f"{unit_id}.{field} 경로는 저장소 기준 상대 POSIX 경로여야 합니다: {path}")
    if ".." in value.split("/") or any(token in value for token in FORBIDDEN_PATH_TOKENS):
        raise ValueError(f"{unit_id}.{field} 경로에 상위 경로 또는 glob을 쓸 수 없습니다: {path}")
    return value


def parse_unit(raw: str, kind: str) -> Unit:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{kind} JSON을 해석할 수 없습니다: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{kind}은(는) JSON object여야 합니다.")
    default_id = kind
    unit_id = data.get("id", default_id)
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise ValueError(f"{kind}.id는 비어 있지 않은 문자열이어야 합니다.")
    unit_id = unit_id.strip()
    if kind == "workstream" and not WORKSTREAM_ID.fullmatch(unit_id):
        raise ValueError("workstream.id는 WS-01 같은 형식이어야 합니다.")
    if kind != "workstream" and unit_id != default_id:
        raise ValueError(f"{kind} unit ID는 {default_id}로 고정됩니다.")
    goal = data.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError(f"{unit_id}.goal은(는) 비어 있지 않은 문자열이어야 합니다.")
    allow = tuple(normalise_path(path, unit_id, "allow") for path in _text_list(data.get("allow"), "allow", unit_id, required=True))
    exclude = tuple(normalise_path(path, unit_id, "exclude") for path in _text_list(data.get("exclude"), "exclude", unit_id))
    tests = _text_list(data.get("tests"), "tests", unit_id, required=True)
    depends_on = _text_list(data.get("depends_on"), "depends_on", unit_id)
    return Unit(unit_id, goal.strip(), allow, exclude, tests, depends_on, kind)


def overlaps(left: str, right: str) -> bool:
    if left == right:
        return True
    return left.endswith("/") and right.startswith(left) or right.endswith("/") and left.startswith(right)


def validate_units(workstreams: list[Unit], common: Unit | None, integration: Unit) -> None:
    if len(workstreams) < 2:
        raise ValueError("V2 병렬 PLAN에는 독립 Workstream이 최소 두 개 필요합니다. 일반 계획은 V1을 사용하세요.")
    ids = [unit.unit_id for unit in workstreams]
    if len(set(ids)) != len(ids):
        raise ValueError("Workstream ID가 중복됩니다.")
    units = ([common] if common else []) + workstreams + [integration]
    valid_dependencies = {unit.unit_id for unit in units} - {"INTEGRATION"}
    for unit in units:
        if len(set(unit.allow)) != len(unit.allow):
            raise ValueError(f"{unit.unit_id}.allow에 중복 경로가 있습니다.")
        for blocked in unit.exclude:
            if any(overlaps(blocked, allowed) for allowed in unit.allow):
                raise ValueError(f"{unit.unit_id}.exclude는 허용 경로와 겹칠 수 없습니다: {blocked}")
        for dependency in unit.depends_on:
            if dependency not in valid_dependencies or dependency == unit.unit_id:
                raise ValueError(f"{unit.unit_id}.depends_on에 유효하지 않은 scope unit이 있습니다: {dependency}")
            if unit.unit_id == "COMMON":
                raise ValueError("COMMON은 선행 조건을 가질 수 없습니다.")
    for index, left_unit in enumerate(units):
        for right_unit in units[index + 1:]:
            for left_path in left_unit.allow:
                for right_path in right_unit.allow:
                    if overlaps(left_path, right_path):
                        raise ValueError(
                            "scope unit 허용 경로가 겹칩니다: "
                            f"{left_unit.unit_id}:{left_path} / {right_unit.unit_id}:{right_path}"
                        )


def wave_map(workstreams: list[Unit], common: Unit | None, integration: Unit) -> dict[int, list[str]]:
    all_workstream_ids = {unit.unit_id for unit in workstreams}
    dependencies = {unit.unit_id: {item for item in unit.depends_on if item in all_workstream_ids} for unit in workstreams}
    remaining = set(all_workstream_ids)
    waves: dict[int, list[str]] = {}
    if common:
        waves[0] = ["COMMON"]
    wave = 1
    while remaining:
        ready = sorted(item for item in remaining if not dependencies[item] & remaining)
        if not ready:
            raise ValueError("Workstream depends_on에 순환 의존성이 있습니다.")
        waves[wave] = ready
        remaining.difference_update(ready)
        wave += 1
    waves[wave] = ["INTEGRATION"]
    return waves


def markdown_cell(value: str) -> str:
    return value.replace("|", "&#124;").replace("\n", " ")


def display_items(values: tuple[str, ...]) -> str:
    return ", ".join(f"`{markdown_cell(item)}`" for item in values) if values else "-"


def table_row(unit: Unit) -> str:
    return "| " + " | ".join(
        (
            unit.unit_id,
            markdown_cell(unit.goal),
            display_items(unit.allow),
            display_items(unit.exclude),
            display_items(unit.depends_on),
            display_items(unit.tests),
        )
    ) + " |"


def phase_block(index: int, name: str) -> str:
    return "\n".join(
        (
            f"## Phase {index}. {name}",
            "### 목표",
            f"- {name} 범위를 선언된 scope unit과 완료 조건 안에서 수행한다.",
            "",
            "### 구현 태스크",
            "- [ ] 선언된 scope unit과 허용 경로를 확인한다.",
            "- [ ] 범위 밖 변경 요구는 BLOCKED 또는 새 계획으로 분리한다.",
            "",
            "### 자체 테스트",
            "- [ ] 해당 scope unit의 선언된 테스트를 실행하고 결과를 기록한다.",
            "- [ ] 다음 Phase 전 범위·diff·체크 상태를 확인한다.",
            "",
            "### 이슈 및 수정",
            "- [ ] 발견 이슈 없음",
            "",
            "### 완료 조건",
            "- [ ] 구현 태스크 완료",
            "- [ ] 자체 테스트 완료",
            "- [ ] Lead가 범위와 실제 diff를 확인",
            "- [ ] 다음 Phase 진행 가능",
            "",
        )
    )


def plan_text(filename: str, created_at: str, args: argparse.Namespace, workstreams: list[Unit], common: Unit | None, integration: Unit, waves: dict[int, list[str]]) -> str:
    references = [item.strip() for item in args.reference if item.strip()]
    if args.previous_plan and args.previous_plan.strip():
        references.insert(0, f"이전 개발 계획: {args.previous_plan.strip()}")
    phases = [item.strip() for item in args.phase if item.strip()] or ["병렬 Workstream 구현", "통합 검증"]
    serial_units = ([common] if common else []) + [integration]
    phase_summary = "\n".join(f"- [ ] Phase {index} 완료 — {name}" for index, name in enumerate(phases, start=1))
    phase_sections = "\n".join(phase_block(index, name) for index, name in enumerate(phases, start=1))
    wave_lines = "\n".join(f"- Wave {number}: {', '.join(unit_ids)}" for number, unit_ids in waves.items())
    scope_items = "\n".join(f"- {item.strip()}" for item in args.scope if item.strip()) or "- 선언된 Workstream 및 직렬 scope unit"
    exclude_items = "\n".join(f"- {item.strip()}" for item in args.exclude if item.strip()) or "- 선언되지 않은 기능·경로·의존성·공개 API 변경"
    reference_items = "\n".join(f"- {item}" for item in references) or "- 현재 프로젝트 코드·테스트·관련 문서"
    return "\n".join(
        (
            f"# {filename}",
            "",
            f"작성 일시: `{created_at}`",
            "",
            "이 문서는 병렬 개발 범위를 scope unit과 Wave로 고정하고, 무단 경로 변경과 병렬 충돌을 막기 위한 master 계획이다.",
            "",
            "## 개발 목적",
            args.purpose.strip(),
            "",
            "## 개발 범위",
            scope_items,
            "",
            "## 제외 범위",
            exclude_items,
            "",
            "## 참조 문서",
            reference_items,
            "",
            "## 공통 진행 규칙",
            "- V2는 독립 Workstream 두 개 이상, 비중복 허용 경로, 독립 테스트가 있을 때만 사용한다.",
            "- 각 scope unit은 선언된 허용 경로·제외 경로·선행 조건·테스트를 벗어나지 않는다.",
            "- COMMON은 Wave 0에서 직렬로, Workstream은 Wave 1 이상에서, INTEGRATION은 마지막 Wave에서 실행한다.",
            "- 계획상 scope unit은 정확히 하나의 Wave에 속한다. 실행 중 REWORK-WS-*는 실행 기록의 직렬 재작업 단위다.",
            "- 각 Phase는 앞선 Phase의 자체 테스트가 끝난 뒤에만 시작한다.",
            "- 범위 밖 기능·리팩터링·의존성·공개 API 변경은 완료 처리하지 않고 BLOCKED 또는 새 계획으로 분리한다.",
            "",
            "## Workstream 맵",
            "| ID | 목표 | 허용 경로 | 제외 경로 | 선행 조건 | 테스트 |",
            "|---|---|---|---|---|---|",
            *[table_row(unit) for unit in workstreams],
            "",
            "## 직렬 scope unit",
            "| ID | 목표 | 허용 경로 | 제외 경로 | 선행 조건 | 테스트 |",
            "|---|---|---|---|---|---|",
            *[table_row(unit) for unit in serial_units],
            "",
            "## 병렬 실행 Wave",
            wave_lines,
            "",
            "## Phase 상태 요약",
            phase_summary,
            "",
            "## QA 관점",
            "- [ ] Workstream 간 허용 경로가 겹치지 않고 각 Worker diff가 자기 scope unit에만 속하는지 검토한다.",
            "- [ ] COMMON·INTEGRATION·REWORK가 직렬 scope unit으로 처리되는지 검토한다.",
            "- [ ] 범위 밖 변경·테스트 누락·통합 회귀를 독립적으로 검토한다.",
            "",
            phase_sections,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"프로젝트 루트가 없습니다: {root}")
        workstreams = [parse_unit(raw, "workstream") for raw in args.workstream]
        common = parse_unit(args.common, "COMMON") if args.common else None
        integration = parse_unit(args.integration, "INTEGRATION")
        validate_units(workstreams, common, integration)
        waves = wave_map(workstreams, common, integration)
        if args.timestamp:
            moment = dt.datetime.strptime(args.timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=dt.timezone.utc)
        else:
            moment = dt.datetime.now().astimezone()
        output_dir = root / "dev-plan" / "parallel"
        path = output_dir / f"parallel_{moment.strftime('%Y%m%d_%H%M%S')}.md"
        output_dir.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(plan_text(path.name, moment.isoformat(timespec="seconds"), args, workstreams, common, integration, waves))
    except (OSError, ValueError) as exc:
        report = {"status": "PARALLEL_PLAN_CREATE_FAILED", "error": str(exc)}
        print(json.dumps(report, ensure_ascii=False) if args.format == "json" else f"PARALLEL_PLAN_CREATE_FAILED: {exc}", file=sys.stderr)
        return 2
    report = {"status": "PARALLEL_PLAN_CREATED", "path": str(path), "workstreams": len(workstreams), "waves": len(waves)}
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else f"PARALLEL_PLAN_CREATED\npath: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
