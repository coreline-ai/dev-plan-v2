from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def complete_spec() -> dict[str, Any]:
    return {
        "purpose": "계획 오케스트레이션을 안전하게 구현한다.",
        "scope": ["scripts/**", "tests/**"],
        "excludes": ["UI 변경"],
        "references": ["README.md"],
        "phases": [
            {
                "name": "코어 구현",
                "goal": "파서와 상태 전이를 구현한다.",
                "tasks": [
                    {
                        "title": "파서 구현",
                        "objective": "계획 문서를 결정적으로 파싱한다.",
                        "allowed_paths": ["scripts/**"],
                        "allowed_new_paths": ["scripts/**"],
                        "read_paths": ["scripts/**", "tests/**"],
                        "dependencies": [],
                        "complexity": "ROUTINE",
                        "acceptance_criteria": ["단위 테스트 통과"],
                        "tests": [
                            {
                                "title": "단위 테스트",
                                "kind": "command",
                                "argv": ["python3.11", "-m", "pytest"],
                                "cwd": ".",
                                "timeout_seconds": 300,
                                "expected_exit_codes": [0],
                                "env_allowlist": ["PATH", "LANG", "LC_ALL", "TMPDIR"],
                                "network_required": False,
                                "covers_paths": ["scripts/**", "tests/**"],
                                "expected": "테스트가 종료 코드 0으로 통과한다.",
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def spec_file(tmp_path: Path, complete_spec: dict[str, Any]) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(complete_spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def run_script(name: str, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture
def cli():
    return run_script
