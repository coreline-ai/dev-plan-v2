#!/usr/bin/env python3
"""Check one isolated scope-unit diff against a parallel master plan.

The command deliberately accepts one `--scope-unit` and that unit's own
`--changed-file` list only. It is not an aggregate-diff checker.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_PATH_TOKENS = set("*?[]{}")


@dataclass(frozen=True)
class Unit:
    unit_id: str
    allow: tuple[str, ...]
    exclude: tuple[str, ...]


def split_cells(line: str) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError("Markdown 표 행이 아닙니다.")
    return [cell.strip() for cell in line[1:-1].split("|")]


def items(cell: str) -> tuple[str, ...]:
    if cell.strip() in {"", "-"}:
        return ()
    raw = re.sub(r"`([^`]*)`", r"\1", cell).replace("&#124;", "|")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def section_body(text: str, heading: str) -> str:
    found = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    if not found:
        raise ValueError(f"필수 섹션이 없습니다: {heading}")
    next_heading = re.search(r"^## (?!#)", text[found.end():], re.MULTILINE)
    end = found.end() + next_heading.start() if next_heading else len(text)
    return text[found.end():end]


def read_units(text: str, heading: str) -> list[Unit]:
    lines = [line for line in section_body(text, heading).splitlines() if line.strip()]
    if len(lines) < 3:
        raise ValueError(f"{heading} 표가 비어 있습니다.")
    if split_cells(lines[0]) != ["ID", "목표", "허용 경로", "제외 경로", "선행 조건", "테스트"]:
        raise ValueError(f"{heading} 표 헤더가 올바르지 않습니다.")
    result: list[Unit] = []
    for line in lines[2:]:
        row = split_cells(line)
        if len(row) != 6:
            raise ValueError(f"{heading} 표 열 수가 올바르지 않습니다.")
        result.append(Unit(row[0], items(row[2]), items(row[3])))
    return result


def read_plan(path: Path) -> list[Unit]:
    text = path.read_text(encoding="utf-8")
    return read_units(text, "Workstream 맵") + read_units(text, "직렬 scope unit")


def normalise_changed_path(path: str) -> str:
    value = path.strip()
    if not value or value.startswith("/") or value.startswith("~") or "\\" in value:
        raise ValueError(f"changed file은 저장소 기준 상대 POSIX 경로여야 합니다: {path}")
    if ".." in value.split("/") or any(token in value for token in FORBIDDEN_PATH_TOKENS):
        raise ValueError(f"changed file에 상위 경로 또는 glob을 쓸 수 없습니다: {path}")
    return value


def matches(path: str, allowed: str) -> bool:
    return path.startswith(allowed) if allowed.endswith("/") else path == allowed


def effective_unit(units: list[Unit], requested: str) -> tuple[Unit, list[Unit]]:
    if requested.startswith("REWORK-"):
        base_id = requested.removeprefix("REWORK-")
        base = next((unit for unit in units if unit.unit_id == base_id and base_id.startswith("WS-")), None)
        if base is None:
            raise ValueError(f"REWORK 대상 Workstream을 찾을 수 없습니다: {requested}")
        rework = Unit(requested, base.allow, base.exclude)
        return rework, [rework if unit.unit_id == base_id else unit for unit in units]
    unit = next((item for item in units if item.unit_id == requested), None)
    if unit is None:
        raise ValueError(f"scope unit을 찾을 수 없습니다: {requested}")
    return unit, units


def check(units: list[Unit], requested: str, changed_files: list[str]) -> tuple[str, list[dict[str, object]]]:
    current, ownership_units = effective_unit(units, requested)
    details: list[dict[str, object]] = []
    has_ambiguous = False
    has_violation = False
    for raw_path in changed_files:
        path = normalise_changed_path(raw_path)
        owners = [unit.unit_id for unit in ownership_units if any(matches(path, allowed) for allowed in unit.allow)]
        excluded = any(matches(path, blocked) for blocked in current.exclude)
        allowed_here = current.unit_id in owners and not excluded
        if len(owners) > 1:
            outcome = "ambiguous"
            has_ambiguous = True
        elif not allowed_here:
            outcome = "violation"
            has_violation = True
        else:
            outcome = "ok"
        details.append({"path": path, "owners": owners, "outcome": outcome})
    if has_ambiguous:
        return "SCOPE_AMBIGUOUS", details
    if has_violation:
        return "SCOPE_VIOLATION", details
    return "SCOPE_OK", details


def main(argv: list[str] | None = None) -> int:
    command = argparse.ArgumentParser(description="한 scope unit의 격리 changed-file 목록만 검사합니다.")
    command.add_argument("plan")
    command.add_argument("--scope-unit", required=True, help="WS-01, COMMON, INTEGRATION 또는 REWORK-WS-01")
    command.add_argument("--changed-file", action="append", default=[], help="해당 worktree의 changed file (반복 가능)")
    command.add_argument("--format", choices=("text", "json"), default="text")
    args = command.parse_args(argv)
    try:
        units = read_plan(Path(args.plan).expanduser().resolve())
        status, details = check(units, args.scope_unit, args.changed_file)
        report = {"status": status, "scope_unit": args.scope_unit, "files": details}
        code = 0 if status == "SCOPE_OK" else 1
    except (OSError, UnicodeError, ValueError) as exc:
        report = {"status": "SCOPE_AMBIGUOUS", "scope_unit": args.scope_unit, "error": str(exc), "files": []}
        code = 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["status"])
        if "error" in report:
            print(f"- {report['error']}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
