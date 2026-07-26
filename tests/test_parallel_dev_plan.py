from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1_NEW_PLAN = Path.home() / ".codex" / "skills" / "dev-plan-generator" / "scripts" / "new_dev_plan.py"


def spec(unit_id: str, goal: str, allow: list[str], tests: list[str], *, exclude: list[str] | None = None, depends_on: list[str] | None = None) -> str:
    return json.dumps(
        {
            "id": unit_id,
            "goal": goal,
            "allow": allow,
            "exclude": exclude or [],
            "tests": tests,
            "depends_on": depends_on or [],
        },
        ensure_ascii=False,
    )


def create_plan(tmp_path: Path, cli, stamp: str = "20260726_160000", *, common: bool = True, previous_plan: str | None = None) -> Path:
    args: list[str] = [
        "--root", str(tmp_path),
        "--purpose", "API와 Web 오류 처리를 병렬로 수정",
        "--scope", "독립 API·Web workstream",
        "--exclude", "공개 API 변경",
        "--reference", "README.md",
        "--workstream", spec("WS-01", "API 오류 처리", ["src/api/", "tests/api/"], ["python3.11 -m pytest tests/api"], exclude=["src/web/"]),
        "--workstream", spec("WS-02", "Web 오류 표시", ["src/web/", "tests/web/"], ["python3.11 -m pytest tests/web"], exclude=["src/api/"]),
        "--integration", spec("INTEGRATION", "통합 검증", ["tests/integration/"], ["python3.11 -m pytest tests/integration"], depends_on=["WS-01", "WS-02"]),
        "--phase", "병렬 구현",
        "--phase", "통합 검증",
        "--timestamp", stamp,
        "--format", "json",
    ]
    if common:
        args.extend(("--common", spec("COMMON", "공통 설정", ["pyproject.toml"], ["python3.11 -m pytest tests/common"])))
    if previous_plan:
        args.extend(("--previous-plan", previous_plan))
    result = cli("new_parallel_dev_plan.py", *args)
    assert result.returncode == 0, result.stderr
    return Path(json.loads(result.stdout)["path"])


def test_creates_v2_master_only_with_v1_core_sections(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli)
    text = plan.read_text(encoding="utf-8")
    assert plan.parent == tmp_path / "dev-plan" / "parallel"
    assert plan.name == "parallel_20260726_160000.md"
    for heading in ("개발 목적", "개발 범위", "제외 범위", "참조 문서", "공통 진행 규칙", "Phase 상태 요약", "QA 관점"):
        assert f"## {heading}" in text
    assert "## Workstream 맵" in text
    assert "## 직렬 scope unit" in text
    assert "- Wave 0: COMMON" in text
    assert "- Wave 1: WS-01, WS-02" in text
    assert "- Wave 2: INTEGRATION" in text
    assert "## 실행 기록" not in text
    assert "requested model" not in text
    assert "host actual model" not in text
    assert cli("validate_parallel_dev_plan.py", plan).returncode == 0

    before = plan.read_bytes()
    collision = create_collision(tmp_path, cli)
    assert collision.returncode == 2
    assert plan.read_bytes() == before


def create_collision(tmp_path: Path, cli):
    return cli(
        "new_parallel_dev_plan.py", "--root", tmp_path, "--purpose", "충돌",
        "--workstream", spec("WS-01", "A", ["src/a/"], ["pytest a"]),
        "--workstream", spec("WS-02", "B", ["src/b/"], ["pytest b"]),
        "--integration", spec("INTEGRATION", "I", ["tests/i/"], ["pytest i"]),
        "--timestamp", "20260726_160000",
    )


def test_previous_plan_is_first_reference_and_original_is_unchanged(tmp_path: Path, cli) -> None:
    previous = tmp_path / "dev-plan" / "implement_20260725_120000.md"
    previous.parent.mkdir(parents=True)
    previous.write_text("historical V1 plan\n", encoding="utf-8")
    before = previous.read_bytes()
    plan = create_plan(tmp_path, cli, "20260726_160001", previous_plan="dev-plan/implement_20260725_120000.md")
    references = plan.read_text(encoding="utf-8").split("## 참조 문서\n", 1)[1].split("\n## 공통 진행 규칙", 1)[0]
    assert references.splitlines()[0] == "- 이전 개발 계획: dev-plan/implement_20260725_120000.md"
    assert previous.read_bytes() == before


def test_rejects_single_workstream_and_uses_no_v2_output(tmp_path: Path, cli) -> None:
    result = cli(
        "new_parallel_dev_plan.py", "--root", tmp_path, "--purpose", "단일 작업",
        "--workstream", spec("WS-01", "A", ["src/a/"], ["pytest a"]),
        "--integration", spec("INTEGRATION", "I", ["tests/i/"], ["pytest i"]),
        "--format", "json",
    )
    assert result.returncode == 2
    assert "V1" in json.loads(result.stderr)["error"]
    assert not (tmp_path / "dev-plan" / "parallel").exists()


def test_v1_and_v2_output_families_coexist_without_mutation(tmp_path: Path, cli) -> None:
    assert V1_NEW_PLAN.is_file()
    v1 = subprocess.run(
        [sys.executable, str(V1_NEW_PLAN), "--root", str(tmp_path), "--purpose", "일반 수정", "--scope", "src/single.py", "--phase", "구현"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert v1.returncode == 0, v1.stderr
    v1_plan = Path(v1.stdout.strip())
    assert v1_plan.name.startswith("implement_")
    before = v1_plan.read_bytes()

    v2_plan = create_plan(tmp_path, cli, "20260726_160002")
    assert v2_plan.name.startswith("parallel_")
    assert v1_plan.read_bytes() == before
    assert cli("validate_parallel_dev_plan.py", v1_plan).returncode == 1
