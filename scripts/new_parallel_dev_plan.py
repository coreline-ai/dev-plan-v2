#!/usr/bin/env python3
"""Create JSON-source and Markdown-view parallel development plans."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

from parallel_plan_lib import (
    assess_candidate,
    build_plan,
    json_text,
    load_json,
    normalise_candidate,
    render_plan,
)


def _write_pair(output_dir: Path, json_path: Path, markdown_path: Path, plan: dict[str, object]) -> None:
    if json_path.exists() or markdown_path.exists():
        raise FileExistsError(f"plan output already exists: {json_path.stem}")
    output_dir.mkdir(parents=True, exist_ok=True)
    moved_json = False
    with tempfile.TemporaryDirectory(dir=output_dir, prefix=".parallel-plan-") as temporary:
        staging = Path(temporary)
        staged_json = staging / json_path.name
        staged_markdown = staging / markdown_path.name
        staged_json.write_text(json_text(plan), encoding="utf-8", newline="\n")
        staged_markdown.write_text(render_plan(plan, markdown_path.name), encoding="utf-8", newline="\n")
        try:
            os.replace(staged_json, json_path)
            moved_json = True
            os.replace(staged_markdown, markdown_path)
        except OSError:
            if moved_json:
                json_path.unlink(missing_ok=True)
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="적합성 판정을 통과한 병렬 개발 계획 JSON과 Markdown을 생성합니다.")
    parser.add_argument("--root", default=".", help="대상 프로젝트 루트")
    parser.add_argument("--spec", required=True, help="parallel-dev-candidate/v1 JSON 파일")
    parser.add_argument("--timestamp", help="재현 테스트용 YYYYMMDD_HHMMSS")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    report: dict[str, object]
    code = 0
    try:
        root = Path(args.root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"project root does not exist: {root}")
        candidate = normalise_candidate(load_json(Path(args.spec).expanduser().resolve()))
        assessment = assess_candidate(candidate)
        if assessment["decision"] == "SERIAL_RECOMMENDED":
            report = {
                "status": "SERIAL_RECOMMENDED",
                "created": False,
                "assessment": assessment,
                "next": "Use dev-plan-generator (V1) for a serial plan.",
            }
            code = 1
        elif assessment["decision"] == "BLOCKED":
            report = {"status": "PARALLEL_PLAN_BLOCKED", "created": False, "assessment": assessment}
            code = 2
        elif assessment["decision"] == "COMMON_FIRST" and candidate["common"] is None:
            report = {
                "status": "COMMON_REQUIRED",
                "created": False,
                "assessment": assessment,
                "next": "Declare a COMMON unit that owns and tests the shared contracts.",
            }
            code = 1
        else:
            if args.timestamp:
                local_zone = dt.datetime.now().astimezone().tzinfo
                moment = dt.datetime.strptime(args.timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=local_zone)
            else:
                moment = dt.datetime.now().astimezone()
            stamp = moment.strftime("%Y%m%d_%H%M%S")
            plan_id = f"parallel_{stamp}"
            output_dir = root / "dev-plan" / "parallel"
            json_path = output_dir / f"{plan_id}.json"
            markdown_path = output_dir / f"{plan_id}.md"
            plan = build_plan(candidate, assessment, moment.isoformat(timespec="seconds"), plan_id)
            _write_pair(output_dir, json_path, markdown_path, plan)
            report = {
                "status": "PARALLEL_PLAN_CREATED",
                "created": True,
                "decision": assessment["decision"],
                "json_path": str(json_path),
                "markdown_path": str(markdown_path),
                "workstreams": len(candidate["workstreams"]),
                "waves": len(plan["waves"]),
            }
    except (OSError, UnicodeError, ValueError) as exc:
        report = {"status": "PARALLEL_PLAN_CREATE_FAILED", "created": False, "error": str(exc)}
        code = 2
    if args.format == "json":
        stream = sys.stdout if code != 2 else sys.stderr
        print(json.dumps(report, ensure_ascii=False, indent=2), file=stream)
    elif code:
        print(report["status"], file=sys.stderr)
        for reason in report.get("assessment", {}).get("reasons", []):
            print(f"- {reason}", file=sys.stderr)
        if report.get("error"):
            print(f"- {report['error']}", file=sys.stderr)
    else:
        print("PARALLEL_PLAN_CREATED")
        print(f"json: {report['json_path']}")
        print(f"markdown: {report['markdown_path']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
