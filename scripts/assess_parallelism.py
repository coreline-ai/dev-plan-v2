#!/usr/bin/env python3
"""Assess whether candidate responsibility units are safe to run in parallel."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from parallel_plan_lib import assess_candidate, load_json, normalise_candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="필요성·독립성·실제 속도 이점으로 직렬·COMMON 선행·안전한 병렬을 판정합니다.")
    parser.add_argument("spec", help="parallel-dev-candidate/v1 JSON 파일")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        candidate = normalise_candidate(load_json(Path(args.spec).expanduser().resolve()))
        report = assess_candidate(candidate)
    except (OSError, UnicodeError, ValueError) as exc:
        report = {
            "decision": "BLOCKED",
            "reasons": [str(exc)],
            "semantic_blockers": [],
            "shared_contracts": [],
            "coordination_risks": [],
        }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["decision"])
        for reason in report["reasons"]:
            print(f"- {reason}")
    return 0 if report["decision"] in {"PARALLEL_SAFE", "COMMON_FIRST"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
