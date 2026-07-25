#!/usr/bin/env python3
"""Create a v1-plus phased Markdown development plan without overwriting plans."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v1-plus 개발 계획 Markdown을 생성합니다.")
    parser.add_argument("--root", default=".", help="대상 프로젝트 루트")
    parser.add_argument("--output-dir", help="기본값: <root>/dev-plan")
    parser.add_argument("--purpose", required=True, help="개발 목적")
    parser.add_argument("--scope", action="append", default=[], help="개발 범위 (반복 가능)")
    parser.add_argument("--exclude", action="append", default=[], help="제외 범위 (반복 가능)")
    parser.add_argument("--reference", action="append", default=[], help="참조 문서/파일 (반복 가능)")
    parser.add_argument("--phase", action="append", default=[], help="Phase 이름 (반복 가능)")
    parser.add_argument("--test", action="append", default=[], help="자체 테스트 명령 또는 수동 확인 (반복 가능)")
    parser.add_argument("--timestamp", help="재현용 YYYYMMDD_HHMMSS")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def bullets(values: list[str], fallback: str) -> str:
    return "\n".join(f"- {item.strip()}" for item in values if item.strip()) or f"- {fallback}"


def checklist(values: list[str], fallback: str) -> str:
    return "\n".join(f"- [ ] {item.strip()}" for item in values if item.strip()) or f"- [ ] {fallback}"


def plan_text(filename: str, created_at: str, args: argparse.Namespace) -> str:
    phases = [phase.strip() for phase in args.phase if phase.strip()] or ["구현 범위 확정 필요"]
    summary = "\n".join(f"- [ ] Phase {index} 완료 — {phase}" for index, phase in enumerate(phases, start=1))
    phase_sections: list[str] = []
    for index, phase in enumerate(phases, start=1):
        phase_sections.extend(
            [
                f"## Phase {index}. {phase}",
                "### 목표",
                f"- {phase}의 요청된 동작을 구현하고 검증한다.",
                "",
                "### 예상 변경 파일 / 영향 범위",
                bullets(args.scope, "실행 전 변경 파일과 영향 범위를 확인 필요"),
                "",
                "### 구현 태스크",
                checklist([f"{phase} 구현"], "구현 책임 단위를 정의 필요"),
                "",
                "### 자체 테스트",
                checklist(args.test, "실행 전 테스트 명령 또는 수동 확인을 정의 필요"),
                "",
                "### 이슈 및 수정",
                "- [ ] 발견 이슈 없음",
                "",
                "### 완료 조건",
                "- [ ] 구현 태스크 완료",
                "- [ ] 자체 테스트 완료",
                "- [ ] Lead가 diff와 범위를 확인",
                "- [ ] 다음 Phase 진행 가능",
                "",
            ]
        )
    return "\n".join(
        [
            f"# {filename}",
            "",
            f"작성 일시: `{created_at}`",
            "",
            "이 문서는 이번 개발의 범위를 고정하고, 진행 상태와 검증 결과를 남기는 작업 문서다.",
            "",
            "## 개발 목적",
            args.purpose.strip(),
            "",
            "## 개발 범위",
            bullets(args.scope, "실행 전 범위를 확인 필요"),
            "",
            "## 제외 범위",
            bullets(args.exclude, "문서에 없는 기능 확장과 무관한 리팩터링"),
            "",
            "## 참조 문서",
            bullets(args.reference, "프로젝트의 현재 코드와 테스트"),
            "",
            "## 공통 진행 규칙",
            "- 각 Phase는 앞선 Phase의 자체 테스트 완료 후에만 시작한다.",
            "- 구현 중 발생한 이슈는 해당 Phase에서 기록하고 수정한다.",
            "- 체크박스 상태는 실제 diff와 테스트 결과에 맞춘다.",
            "- 문서에 없는 범위 확장은 하지 않는다.",
            "- 기존 프로젝트 API, 공식 SDK, 표준 라이브러리를 우선 검토한다.",
            "",
            "## 실행 상태 및 모델 라우팅",
            "- 계획 상태: DRAFT",
            "- 현재 Phase: Phase 1",
            "- Lead: 실행 전 실제 Sol 모델 기록 (reasoning: high)",
            "- ROUTINE Worker: 실행 전 실제 Terra 모델 기록 (reasoning: medium)",
            "- COMPLEX Worker: 실행 전 실제 Luna 모델 확인; 없으면 BLOCKED 또는 재분해 (reasoning: high)",
            "- Independent QA: 새 Sol 컨텍스트로 실행 전 실제 모델 기록 (reasoning: high)",
            "- 마지막 확인: 미실행",
            "",
            "## Phase 상태 요약",
            summary,
            "",
            "## QA 관점",
            "- [ ] 실패 케이스와 경계값을 검토한다.",
            "- [ ] 회귀 리스크와 실제 테스트 결과를 확인한다.",
            "- [ ] QA 모델·추론 강도·판정을 실행 기록에 남긴다.",
            "",
            *phase_sections,
            "## 최종 결과 요약",
            "- 변경 파일: 없음",
            "- 실행한 테스트: 미실행",
            "- QA 판정: 미실행",
            "- 잔여 리스크 / 후속 과제: 없음",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"프로젝트 루트가 없습니다: {root}")
        output = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "dev-plan"
        if args.timestamp:
            moment = dt.datetime.strptime(args.timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=dt.timezone.utc)
        else:
            moment = dt.datetime.now().astimezone()
        path = output / f"implement_{moment.strftime('%Y%m%d_%H%M%S')}.md"
        output.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(plan_text(path.name, moment.isoformat(timespec="seconds"), args))
    except (OSError, ValueError) as exc:
        report = {"status": "PLAN_CREATE_FAILED", "error": str(exc)}
        print(json.dumps(report, ensure_ascii=False) if args.format == "json" else f"PLAN_CREATE_FAILED: {exc}", file=sys.stderr)
        return 2
    report = {"status": "PLAN_CREATED", "path": str(path), "phases": len(args.phase or ["구현 범위 확정 필요"])}
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else f"PLAN_CREATED\npath: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
