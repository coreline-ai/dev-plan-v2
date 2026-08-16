#!/usr/bin/env python3
"""Shared data model and deterministic helpers for parallel development plans."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

PLAN_SCHEMA = "parallel-dev-plan/v3"
CANDIDATE_SCHEMA = "parallel-dev-candidate/v1"
DECISIONS = {"SERIAL_RECOMMENDED", "COMMON_FIRST", "PARALLEL_SAFE", "BLOCKED"}
RISKS = {"low", "medium", "high", "critical"}
WORKSTREAM_ID = re.compile(r"WS-(?:0[1-9]|[1-9][0-9])$")
FORBIDDEN_PATH_TOKENS = set("*?[]{}")
LEAD_ONLY_PATHS = ("docs/dev-lessons/",)
UNIT_FIELDS = {
    "id", "goal", "write_paths", "allow", "read_context", "exclude_paths", "exclude",
    "depends_on", "tests", "required_capabilities", "risk",
}
CANDIDATE_FIELDS = {
    "schema", "purpose", "scope", "exclude", "references", "previous_plan",
    "semantic_blockers", "shared_contracts", "coordination_risks", "assessment_reasons",
    "common", "workstreams", "integration", "phases", "compliance",
}
PLAN_FIELDS = {
    "schema", "plan_id", "created_at", "purpose", "scope", "exclude", "references",
    "assessment", "common", "workstreams", "integration", "waves", "phases", "compliance",
}


def _strings(value: object, field: str, *, required: bool = False) -> list[str]:
    if value is None:
        values: list[object] = []
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError(f"{field} must be a list of strings")
    result: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} accepts non-empty strings only")
        cleaned = item.strip()
        if cleaned in result:
            raise ValueError(f"{field} contains a duplicate value: {cleaned}")
        result.append(cleaned)
    if required and not result:
        raise ValueError(f"{field} requires at least one value")
    return result


def normalise_repo_path(raw: str, field: str) -> str:
    value = raw.strip()
    if (
        not value
        or value in {".", "./"}
        or value.startswith(("/", "~", "./"))
        or "\\" in value
        or "//" in value
        or "/./" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError(f"{field} must be a canonical repository-relative POSIX path: {raw!r}")
    if ".." in value.split("/") or any(token in value for token in FORBIDDEN_PATH_TOKENS):
        raise ValueError(f"{field} cannot contain parent traversal or glob tokens: {raw!r}")
    return value


def _paths(value: object, field: str, *, required: bool = False) -> list[str]:
    return [normalise_repo_path(item, field) for item in _strings(value, field, required=required)]


def path_matches(path: str, owned: str) -> bool:
    return path.startswith(owned) if owned.endswith("/") else path == owned


def paths_overlap(left: str, right: str) -> bool:
    return left == right or (left.endswith("/") and right.startswith(left)) or (right.endswith("/") and left.startswith(right))


def _unit(raw: object, *, default_id: str | None = None, require_write: bool = True) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("scope unit must be a JSON object")
    unknown = sorted(set(raw) - UNIT_FIELDS)
    if unknown:
        raise ValueError(f"scope unit contains unknown fields: {', '.join(unknown)}")
    unit_id = raw.get("id", default_id)
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise ValueError("scope unit id is required")
    unit_id = unit_id.strip()
    if default_id and unit_id != default_id:
        raise ValueError(f"scope unit id is fixed to {default_id}")
    if default_id is None and not WORKSTREAM_ID.fullmatch(unit_id):
        raise ValueError(f"workstream id must use WS-01..WS-99 format: {unit_id}")
    goal = raw.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError(f"{unit_id}.goal is required")
    write_value = raw.get("write_paths", raw.get("allow"))
    exclude_value = raw.get("exclude_paths", raw.get("exclude"))
    result = {
        "id": unit_id,
        "goal": goal.strip(),
        "write_paths": _paths(write_value, f"{unit_id}.write_paths", required=require_write),
        "read_context": _paths(raw.get("read_context"), f"{unit_id}.read_context"),
        "exclude_paths": _paths(exclude_value, f"{unit_id}.exclude_paths"),
        "depends_on": _strings(raw.get("depends_on"), f"{unit_id}.depends_on"),
        "tests": _strings(raw.get("tests"), f"{unit_id}.tests"),
        "required_capabilities": _strings(raw.get("required_capabilities"), f"{unit_id}.required_capabilities"),
        "risk": raw.get("risk", "medium"),
    }
    if result["risk"] not in RISKS:
        raise ValueError(f"{unit_id}.risk must be one of: {', '.join(sorted(RISKS))}")
    return result


def normalise_candidate(raw: object) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("candidate spec must be a JSON object")
    unknown = sorted(set(raw) - CANDIDATE_FIELDS)
    if unknown:
        raise ValueError(f"candidate spec contains unknown fields: {', '.join(unknown)}")
    schema = raw.get("schema", CANDIDATE_SCHEMA)
    if schema != CANDIDATE_SCHEMA:
        raise ValueError(f"unsupported candidate schema: {schema}")
    purpose = raw.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose is required")
    workstreams_raw = raw.get("workstreams", [])
    if not isinstance(workstreams_raw, list):
        raise ValueError("workstreams must be a list")
    common_raw = raw.get("common")
    integration_raw = raw.get("integration")
    compliance = raw.get("compliance", {})
    if not isinstance(compliance, Mapping):
        raise ValueError("compliance must be a JSON object")
    compliance_unknown = sorted(set(compliance) - {"require_actual_model"})
    if compliance_unknown:
        raise ValueError(f"compliance contains unknown fields: {', '.join(compliance_unknown)}")
    return {
        "schema": CANDIDATE_SCHEMA,
        "purpose": purpose.strip(),
        "scope": _strings(raw.get("scope"), "scope"),
        "exclude": _strings(raw.get("exclude"), "exclude"),
        "references": _strings(raw.get("references"), "references"),
        "previous_plan": raw.get("previous_plan"),
        "semantic_blockers": _strings(raw.get("semantic_blockers"), "semantic_blockers"),
        "shared_contracts": _paths(raw.get("shared_contracts"), "shared_contracts"),
        "coordination_risks": _strings(raw.get("coordination_risks"), "coordination_risks"),
        "assessment_reasons": _strings(raw.get("assessment_reasons"), "assessment_reasons"),
        "common": _unit(common_raw, default_id="COMMON") if common_raw is not None else None,
        "workstreams": [_unit(item) for item in workstreams_raw],
        "integration": _unit(integration_raw, default_id="INTEGRATION", require_write=False) if integration_raw is not None else None,
        "phases": _strings(raw.get("phases"), "phases"),
        "compliance": dict(compliance),
    }


def _ownership_errors(units: Iterable[dict[str, Any]]) -> list[str]:
    materialised = list(units)
    errors: list[str] = []
    for unit in materialised:
        for excluded in unit["exclude_paths"]:
            if any(paths_overlap(excluded, allowed) for allowed in unit["write_paths"]):
                errors.append(f"{unit['id']} exclude path overlaps its write path: {excluded}")
    for index, left in enumerate(materialised):
        for right in materialised[index + 1 :]:
            for left_path in left["write_paths"]:
                for right_path in right["write_paths"]:
                    if paths_overlap(left_path, right_path):
                        errors.append(f"write path ownership overlaps: {left['id']}:{left_path} / {right['id']}:{right_path}")
    return errors


def _lead_only_path_errors(units: Iterable[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for unit in units:
        for path in unit["write_paths"]:
            normalized = path.rstrip("/")
            for reserved in LEAD_ONLY_PATHS:
                reserved_normalized = reserved.rstrip("/")
                if (
                    normalized == reserved_normalized
                    or normalized.startswith(reserved_normalized + "/")
                    or reserved_normalized.startswith(normalized + "/")
                ):
                    errors.append(f"{unit['id']} cannot own Lead-only path {reserved}: {path}")
    return errors


def _dependency_errors(candidate: dict[str, Any]) -> list[str]:
    common = candidate["common"]
    workstreams = candidate["workstreams"]
    integration = candidate["integration"]
    known = {unit["id"] for unit in workstreams}
    if common:
        known.add("COMMON")
        if common["depends_on"]:
            return ["COMMON cannot have dependencies"]
    errors: list[str] = []
    graph: dict[str, set[str]] = {}
    for unit in workstreams:
        dependencies = set(unit["depends_on"])
        invalid = sorted(item for item in dependencies if item not in known or item == unit["id"])
        errors.extend(f"{unit['id']} has an invalid dependency: {item}" for item in invalid)
        graph[unit["id"]] = {item for item in dependencies if item.startswith("WS-")}
    if integration:
        for item in integration["depends_on"]:
            if item not in known or item == "INTEGRATION":
                errors.append(f"INTEGRATION has an invalid dependency: {item}")
    remaining = set(graph)
    while remaining:
        ready = {unit_id for unit_id in remaining if not graph[unit_id] & remaining}
        if not ready:
            errors.append("workstream dependencies contain a cycle")
            break
        remaining -= ready
    return errors


def assess_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    reasons = list(candidate["assessment_reasons"])
    blockers: list[str] = []
    serial: list[str] = []
    workstreams = candidate["workstreams"]
    ids = [unit["id"] for unit in workstreams]
    if len(ids) != len(set(ids)):
        blockers.append("workstream ids are duplicated")
    blockers.extend(_dependency_errors(candidate))
    units = ([candidate["common"]] if candidate["common"] else []) + workstreams + ([candidate["integration"]] if candidate["integration"] else [])
    blockers.extend(_lead_only_path_errors(units))
    ownership = _ownership_errors(units)
    if ownership:
        serial.extend(ownership)
    if len(workstreams) < 2:
        serial.append("fewer than two natural workstreams were identified")
    if not candidate["assessment_reasons"]:
        serial.append("necessity, independence, and parallel benefit were not confirmed")
    for unit in workstreams:
        if not unit["write_paths"]:
            serial.append(f"{unit['id']} has no independent write path")
        if not unit["tests"]:
            serial.append(f"{unit['id']} has no independent test")
    if candidate["semantic_blockers"]:
        serial.extend(f"semantic blocker: {item}" for item in candidate["semantic_blockers"])
    if candidate["coordination_risks"]:
        serial.extend(f"coordination risk remains: {item}" for item in candidate["coordination_risks"])
    if candidate["common"] and not candidate["common"]["tests"]:
        blockers.append("COMMON requires at least one independent test")
    if candidate["common"]:
        for contract in candidate["shared_contracts"]:
            if not any(path_matches(contract, owned) for owned in candidate["common"]["write_paths"]):
                blockers.append(f"COMMON does not own shared contract: {contract}")
    if candidate["integration"] is None:
        blockers.append("integration verification is required")
    elif not candidate["integration"]["tests"]:
        blockers.append("integration requires at least one final test")
    if blockers:
        decision = "BLOCKED"
        reasons.extend(blockers)
    elif serial:
        decision = "SERIAL_RECOMMENDED"
        reasons.extend(serial)
    elif candidate["shared_contracts"]:
        decision = "COMMON_FIRST"
        reasons.append("shared contracts must be fixed before lane work begins")
        if candidate["common"] is None:
            reasons.append("COMMON scope is required before a parallel plan can be created")
    else:
        decision = "PARALLEL_SAFE"
        reasons.append("workstreams have independent goals, write paths, and tests")
    return {
        "decision": decision,
        "reasons": list(dict.fromkeys(reasons)),
        "semantic_blockers": list(candidate["semantic_blockers"]),
        "shared_contracts": list(candidate["shared_contracts"]),
        "coordination_risks": list(candidate["coordination_risks"]),
    }


def wave_map(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    workstreams = candidate["workstreams"]
    graph = {unit["id"]: {item for item in unit["depends_on"] if item.startswith("WS-")} for unit in workstreams}
    remaining = set(graph)
    waves: list[dict[str, Any]] = []
    if candidate["common"]:
        waves.append({"number": 0, "units": ["COMMON"]})
    number = 1
    while remaining:
        ready = sorted(unit_id for unit_id in remaining if not graph[unit_id] & remaining)
        if not ready:
            raise ValueError("workstream dependencies contain a cycle")
        waves.append({"number": number, "units": ready})
        remaining.difference_update(ready)
        number += 1
    waves.append({"number": number, "units": ["INTEGRATION"]})
    return waves


def build_plan(candidate: dict[str, Any], assessment: dict[str, Any], created_at: str, plan_id: str) -> dict[str, Any]:
    if assessment["decision"] not in {"PARALLEL_SAFE", "COMMON_FIRST"}:
        raise ValueError(f"cannot create a parallel plan for decision {assessment['decision']}")
    if assessment["decision"] == "COMMON_FIRST" and candidate["common"] is None:
        raise ValueError("COMMON_FIRST requires a declared COMMON scope unit")
    if candidate["integration"] is None or not candidate["integration"]["tests"]:
        raise ValueError("integration verification with at least one test is required")
    for unit in candidate["workstreams"]:
        if not unit["write_paths"] or not unit["tests"]:
            raise ValueError(f"{unit['id']} requires write_paths and tests")
    references = list(candidate["references"])
    previous = candidate.get("previous_plan")
    if previous:
        if not isinstance(previous, str) or not previous.strip():
            raise ValueError("previous_plan must be a non-empty string")
        references.insert(0, f"이전 개발 계획: {previous.strip()}")
    return {
        "schema": PLAN_SCHEMA,
        "plan_id": plan_id,
        "created_at": created_at,
        "purpose": candidate["purpose"],
        "scope": candidate["scope"] or ["선언된 Workstream과 통합 검증"],
        "exclude": candidate["exclude"] or ["선언되지 않은 기능·경로·의존성·공개 계약 변경"],
        "references": references or ["현재 프로젝트 코드·테스트·관련 문서"],
        "assessment": assessment,
        "common": candidate["common"],
        "workstreams": candidate["workstreams"],
        "integration": candidate["integration"],
        "waves": wave_map(candidate),
        "phases": candidate["phases"] or ["선행 계약 확정", "병렬 Workstream 구현", "통합 검증"],
        "compliance": {"require_actual_model": bool(candidate["compliance"].get("require_actual_model", False))},
    }


def plan_units(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if plan.get("common"):
        result.append(dict(plan["common"]))
    result.extend(dict(unit) for unit in plan.get("workstreams", []))
    if plan.get("integration"):
        result.append(dict(plan["integration"]))
    return result


def validate_plan(plan: object) -> list[str]:
    if not isinstance(plan, Mapping):
        return ["plan must be a JSON object"]
    errors: list[str] = []
    unknown = sorted(set(plan) - PLAN_FIELDS)
    if unknown:
        errors.append(f"plan contains unknown fields: {', '.join(unknown)}")
    if plan.get("schema") != PLAN_SCHEMA:
        errors.append(f"schema must be {PLAN_SCHEMA}")
    for field in ("plan_id", "created_at", "purpose"):
        if not isinstance(plan.get(field), str) or not str(plan.get(field)).strip():
            errors.append(f"{field} is required")
    assessment = plan.get("assessment")
    if not isinstance(assessment, Mapping) or assessment.get("decision") not in {"PARALLEL_SAFE", "COMMON_FIRST"}:
        errors.append("assessment decision must be PARALLEL_SAFE or COMMON_FIRST")
    try:
        candidate = normalise_candidate(
            {
                "purpose": plan.get("purpose", ""),
                "scope": plan.get("scope", []),
                "exclude": plan.get("exclude", []),
                "references": plan.get("references", []),
                "shared_contracts": assessment.get("shared_contracts", []) if isinstance(assessment, Mapping) else [],
                "semantic_blockers": assessment.get("semantic_blockers", []) if isinstance(assessment, Mapping) else [],
                "coordination_risks": assessment.get("coordination_risks", []) if isinstance(assessment, Mapping) else [],
                "common": plan.get("common"),
                "workstreams": plan.get("workstreams", []),
                "integration": plan.get("integration"),
                "phases": plan.get("phases", []),
                "compliance": plan.get("compliance", {}),
            }
        )
        errors.extend(_dependency_errors(candidate))
        errors.extend(_lead_only_path_errors(plan_units(plan)))
        errors.extend(_ownership_errors(plan_units(plan)))
        if len(candidate["workstreams"]) < 2:
            errors.append("at least two workstreams are required")
        if not candidate["phases"]:
            errors.append("at least one phase is required")
        for unit in candidate["workstreams"]:
            if not unit["write_paths"] or not unit["tests"]:
                errors.append(f"{unit['id']} requires write_paths and tests")
        if candidate["integration"] is None or not candidate["integration"]["tests"]:
            errors.append("integration final tests are required")
        if candidate["common"] is not None and not candidate["common"]["tests"]:
            errors.append("COMMON tests are required")
        expected_waves = wave_map(candidate)
        if plan.get("waves") != expected_waves:
            errors.append("waves do not match scope unit dependencies")
        if isinstance(assessment, Mapping) and assessment.get("decision") == "COMMON_FIRST" and candidate["common"] is None:
            errors.append("COMMON_FIRST requires COMMON")
    except ValueError as exc:
        errors.append(str(exc))
    return list(dict.fromkeys(errors))


def _cell(value: str) -> str:
    return value.replace("|", "&#124;").replace("\n", " ")


def _items(values: Iterable[str]) -> str:
    values = list(values)
    return "<br>".join(f"`{_cell(item)}`" for item in values) if values else "-"


def _unit_row(unit: Mapping[str, Any]) -> str:
    return "| " + " | ".join(
        (
            str(unit["id"]),
            _cell(str(unit["goal"])),
            _items(unit["write_paths"]),
            _items(unit["read_context"]),
            _items(unit["depends_on"]),
            _items(unit["tests"]),
            str(unit["risk"]),
        )
    ) + " |"


def _phase_block(index: int, name: str) -> str:
    return "\n".join(
        (
            f"## Phase {index}. {name}",
            "### 목표",
            f"- {name} 범위를 선언된 책임과 완료 조건 안에서 수행한다.",
            "",
            "### 구현 태스크",
            "- [ ] 시작 전 scope unit, baseline, write 경로를 확인한다.",
            "- [ ] 범위 밖 요구는 직렬 전환, BLOCKED 또는 새 계획으로 분리한다.",
            "",
            "### 자체 테스트",
            "- [ ] 선언된 테스트를 실행하고 명령과 종료 코드를 기록한다.",
            "- [ ] 실제 Git diff와 scope 결과를 확인한다.",
            "",
            "### 이슈 및 수정",
            "- [ ] 발견 이슈 없음",
            "",
            "### 완료 조건",
            "- [ ] 구현 태스크 완료",
            "- [ ] 자체 테스트 완료",
            "- [ ] 범위와 실제 diff 확인",
            "- [ ] 위험도에 맞는 QA 완료",
            "",
        )
    )


def render_plan(plan: Mapping[str, Any], markdown_filename: str) -> str:
    phases = list(plan["phases"])
    common = plan.get("common")
    integration = plan["integration"]
    assessment = plan["assessment"]
    serial_rows = ([_unit_row(common)] if common else []) + [_unit_row(integration)]
    phase_sections = "\n".join(_phase_block(index, name) for index, name in enumerate(phases, 1))
    return "\n".join(
        (
            f"# {markdown_filename}",
            "",
            f"작성 일시: `{plan['created_at']}`",
            f"계획 정본: `{Path(markdown_filename).with_suffix('.json').name}`",
            "",
            "이 문서는 자연스럽게 독립된 작업만 안전하게 병렬 실행하기 위한 master 계획이다.",
            "",
            "## 개발 목적",
            str(plan["purpose"]),
            "",
            "## 병렬화 판정",
            f"- 결정: `{assessment['decision']}`",
            *[f"- 근거: {item}" for item in assessment["reasons"]],
            *[f"- 공유 계약: `{item}`" for item in assessment["shared_contracts"]],
            *[f"- 조율 위험: {item}" for item in assessment["coordination_risks"]],
            "",
            "## 개발 범위",
            *[f"- {item}" for item in plan["scope"]],
            "",
            "## 제외 범위",
            *[f"- {item}" for item in plan["exclude"]],
            "",
            "## 참조 문서",
            *[f"- {item}" for item in plan["references"]],
            "",
            "## 공통 진행 규칙",
            "- 책임 단위를 먼저 설계하고 병렬화는 적합성 판정 결과로만 선택한다.",
            "- COMMON이 있으면 완료 commit을 모든 Worker의 lane baseline으로 사용한다.",
            "- Worker는 write 경로만 수정하고 read context는 읽기 전용으로 취급한다.",
            "- 실제 Git 변경, 테스트 종료 코드, 위험도 기반 QA가 확인된 결과만 통합한다.",
            "- 모델 metadata는 compliance 설정이 요구할 때만 완료 gate로 사용한다.",
            "",
            "## Workstream 맵",
            "| ID | 목표 | Write 경로 | Read context | 선행 조건 | 테스트 | 위험도 |",
            "|---|---|---|---|---|---|---|",
            *[_unit_row(unit) for unit in plan["workstreams"]],
            "",
            "## 직렬 scope unit",
            "| ID | 목표 | Write 경로 | Read context | 선행 조건 | 테스트 | 위험도 |",
            "|---|---|---|---|---|---|---|",
            *serial_rows,
            "",
            "## 병렬 실행 Wave",
            *[f"- Wave {wave['number']}: {', '.join(wave['units'])}" for wave in plan["waves"]],
            "",
            "## Phase 상태 요약",
            *[f"- [ ] Phase {index} 완료 — {name}" for index, name in enumerate(phases, 1)],
            "",
            "## QA 관점",
            "- [ ] 의미적으로 결합된 작업을 경로만 나눠 병렬화하지 않았는지 검토한다.",
            "- [ ] 실제 변경에 untracked·rename·delete가 포함됐는지 검토한다.",
            "- [ ] 공유 계약, lane baseline, 최종 회귀 테스트를 검토한다.",
            "- [ ] 위험도에 맞는 독립 검토 증거를 확인한다.",
            "",
            phase_sections,
        )
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
