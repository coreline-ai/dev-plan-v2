#!/usr/bin/env python3
"""Create a small Markdown implementation plan without overwriting an existing plan."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="간단한 개발 계획 Markdown을 생성합니다.")
    value.add_argument("--root", default=".", help="대상 프로젝트 루트")
    value.add_argument("--output-dir", help="기본값: <root>/dev-plan")
    value.add_argument("--purpose", required=True, help="개발 목적")
    value.add_argument("--scope", action="append", default=[], help="변경 범위 (반복 가능)")
    value.add_argument("--exclude", action="append", default=[], help="제외 범위 (반복 가능)")
    value.add_argument("--reference", action="append", default=[], help="참조 파일/문서 (반복 가능)")
    value.add_argument("--phase", action="append", default=[], help="Phase 이름 (반복 가능)")
    value.add_argument("--timestamp", help="재현용 YYYYMMDD_HHMMSS")
    value.add_argument("--format", choices=["text", "json"], default="text")
    return value


def bullet(values: list[str], fallback: str) -> str:
    return "\n".join(f"- {item}" for item in values) if values else f"- {fallback}"


def plan_text(filename: str, created_at: str, args: argparse.Namespace) -> str:
    phases = args.phase or ["구현"]
    sections: list[str] = [
        f"# {filename}",
        "",
        f"작성 일시: `{created_at}`",
        "",
        "## 개발 목적",
        args.purpose.strip(),
        "",
        "## 범위",
        bullet(args.scope, "구현 전에 범위를 보완한다."),
        "",
        "## 제외 범위",
        bullet(args.exclude, "명시되지 않은 기능 확장"),
        "",
        "## 참조",
        bullet(args.reference, "프로젝트의 현재 코드와 테스트"),
        "",
        "## 실행 규칙",
        "- 명시적인 실행 요청이 있을 때만 코드를 수정한다.",
        "- 각 Phase 뒤 실제 테스트 결과를 기록한다.",
        "- 막힌 항목은 완료로 표시하지 않는다.",
        "",
    ]
    for index, phase in enumerate(phases, start=1):
        sections.extend(
            [
                f"## Phase {index}. {phase.strip()}",
                "- [ ] 구현",
                "  - 변경 범위: 위 범위에서 필요한 파일만 수정",
                "  - 완료 기준: 요청한 동작을 확인",
                "  - 검증: 프로젝트에 맞는 테스트 실행",
                "",
            ]
        )
    sections.extend(
        [
            "## QA 체크리스트",
            "- [ ] 변경 diff가 계획 범위와 일치한다.",
            "- [ ] 실제 실행한 테스트와 결과를 기록했다.",
            "- [ ] 열린 문제 또는 남은 위험을 기록했다.",
            "",
            "## 실행 기록",
            "- 상태: 계획됨",
            "- 변경 파일: 없음",
            "- 테스트: 미실행",
            "- 메모: 없음",
            "",
        ]
    )
    return "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"프로젝트 루트가 없습니다: {root}")
        output = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "dev-plan"
        if args.timestamp:
            moment = dt.datetime.strptime(args.timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=dt.timezone.utc)
        else:
            moment = dt.datetime.now().astimezone()
        stamp = moment.strftime("%Y%m%d_%H%M%S")
        path = output / f"implement_{stamp}.md"
        output.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(plan_text(path.name, moment.isoformat(timespec="seconds"), args))
    except (OSError, ValueError) as exc:
        report = {"status": "PLAN_CREATE_FAILED", "error": str(exc)}
        print(json.dumps(report, ensure_ascii=False) if args.format == "json" else f"PLAN_CREATE_FAILED: {exc}", file=sys.stderr)
        return 2

    report = {"status": "PLAN_CREATED", "path": str(path), "phases": len(args.phase or ["구현"])}
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("PLAN_CREATED")
        print(f"path: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
