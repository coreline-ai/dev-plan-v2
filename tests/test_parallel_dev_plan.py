from __future__ import annotations

import json
from pathlib import Path


def unit(
    unit_id: str,
    goal: str,
    write_paths: list[str],
    tests: list[str],
    *,
    read_context: list[str] | None = None,
    depends_on: list[str] | None = None,
    risk: str = "medium",
) -> dict[str, object]:
    return {
        "id": unit_id,
        "goal": goal,
        "write_paths": write_paths,
        "read_context": read_context or [],
        "exclude_paths": [],
        "depends_on": depends_on or [],
        "tests": tests,
        "required_capabilities": ["python"],
        "risk": risk,
    }


def candidate(*, common: bool = True, blockers: list[str] | None = None) -> dict[str, object]:
    contract = ["src/contracts/error.py"] if common else []
    dependency = ["COMMON"] if common else []
    return {
        "schema": "parallel-dev-candidate/v1",
        "purpose": "API와 Web 오류 처리를 안전하게 구현",
        "scope": ["독립 API·Web 책임"],
        "exclude": ["인증 흐름 변경"],
        "references": ["README.md"],
        "semantic_blockers": blockers or [],
        "shared_contracts": contract,
        "coordination_risks": [],
        "assessment_reasons": [
            "모든 lane은 최소 구현에 필요하고 독립 테스트가 가능하며 동시 실행 이점이 명확하다"
        ],
        "common": unit("COMMON", "공통 오류 계약", contract, ["pytest tests/contracts"], risk="high") if common else None,
        "workstreams": [
            unit("WS-01", "API 오류 처리", ["src/api/", "tests/api/"], ["pytest tests/api"], read_context=contract, depends_on=dependency),
            unit("WS-02", "Web 오류 표시", ["src/web/", "tests/web/"], ["pytest tests/web"], read_context=contract, depends_on=dependency),
        ],
        "integration": unit("INTEGRATION", "전체 회귀 검증", [], ["pytest"], depends_on=["WS-01", "WS-02"], risk="high"),
        "phases": ["공통 계약", "병렬 구현", "통합 검증"] if common else ["병렬 구현", "통합 검증"],
        "compliance": {"require_actual_model": False},
    }


def write_spec(tmp_path: Path, value: dict[str, object], name: str = "candidate.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def create_plan(tmp_path: Path, cli, stamp: str = "20260813_120000", *, common: bool = True) -> Path:
    spec = write_spec(tmp_path, candidate(common=common), f"candidate-{stamp}.json")
    result = cli(
        "new_parallel_dev_plan.py",
        "--root",
        tmp_path,
        "--spec",
        spec,
        "--timestamp",
        stamp,
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    return Path(json.loads(result.stdout)["json_path"])


def test_creates_json_source_and_matching_markdown(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli)
    markdown = plan.with_suffix(".md")
    payload = json.loads(plan.read_text(encoding="utf-8"))
    text = markdown.read_text(encoding="utf-8")
    assert payload["schema"] == "parallel-dev-plan/v3"
    assert payload["assessment"]["decision"] == "COMMON_FIRST"
    assert payload["waves"] == [
        {"number": 0, "units": ["COMMON"]},
        {"number": 1, "units": ["WS-01", "WS-02"]},
        {"number": 2, "units": ["INTEGRATION"]},
    ]
    assert "계획 정본: `parallel_20260813_120000.json`" in text
    assert "## Workstream 맵" in text
    assert cli("validate_parallel_dev_plan.py", plan).returncode == 0
    assert cli("validate_parallel_dev_plan.py", markdown).returncode == 0


def test_parallel_safe_without_common_and_optional_integration_writes(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli, "20260813_120001", common=False)
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["assessment"]["decision"] == "PARALLEL_SAFE"
    assert payload["integration"]["write_paths"] == []
    assert payload["waves"][0] == {"number": 1, "units": ["WS-01", "WS-02"]}


def test_serial_recommendation_creates_no_v2_files(tmp_path: Path, cli) -> None:
    value = candidate(common=False, blockers=["두 작업이 같은 상태 모델을 동시에 설계한다"])
    spec = write_spec(tmp_path, value)
    result = cli("new_parallel_dev_plan.py", "--root", tmp_path, "--spec", spec, "--format", "json")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "SERIAL_RECOMMENDED"
    assert report["created"] is False
    assert report["next"] == "Use dev-plan-generator (V1) for a serial plan."
    assert not (tmp_path / "dev-plan" / "parallel").exists()
    assert not list(tmp_path.rglob("parallel_*.execution.json"))
    assert not list(tmp_path.rglob("parallel_*.outcomes.json"))


def test_parallel_plan_creation_publishes_one_json_markdown_pair_only(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli, "20260813_120004", common=False)
    output_files = sorted(item.name for item in plan.parent.iterdir())
    assert output_files == [
        "parallel_20260813_120004.json",
        "parallel_20260813_120004.md",
    ]


def test_previous_v1_plan_is_referenced_without_mutation(tmp_path: Path, cli) -> None:
    previous = tmp_path / "dev-plan" / "implement_20260812_120000.md"
    previous.parent.mkdir(parents=True)
    previous.write_text("historical V1\n", encoding="utf-8")
    before = previous.read_bytes()
    value = candidate(common=False)
    value["previous_plan"] = "dev-plan/implement_20260812_120000.md"
    spec = write_spec(tmp_path, value)
    result = cli(
        "new_parallel_dev_plan.py", "--root", tmp_path, "--spec", spec,
        "--timestamp", "20260813_120002", "--format", "json",
    )
    assert result.returncode == 0, result.stderr
    plan = Path(json.loads(result.stdout)["json_path"])
    assert json.loads(plan.read_text(encoding="utf-8"))["references"][0].startswith("이전 개발 계획:")
    assert previous.read_bytes() == before


def test_pair_creation_is_collision_safe(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli, "20260813_120003", common=False)
    before_json, before_md = plan.read_bytes(), plan.with_suffix(".md").read_bytes()
    spec = write_spec(tmp_path, candidate(common=False), "again.json")
    collision = cli(
        "new_parallel_dev_plan.py", "--root", tmp_path, "--spec", spec,
        "--timestamp", "20260813_120003",
    )
    assert collision.returncode == 2
    assert plan.read_bytes() == before_json
    assert plan.with_suffix(".md").read_bytes() == before_md


def test_dev_lesson_directory_is_reserved_for_post_qa_lead(tmp_path: Path, cli) -> None:
    for write_path in ("docs/", "docs/dev-lessons/", "docs/dev-lessons/DL-test.md"):
        value = candidate(common=False)
        value["workstreams"][0]["write_paths"] = [write_path]
        spec = write_spec(tmp_path, value, f"reserved-{len(write_path)}.json")
        assessed = cli("assess_parallelism.py", spec, "--format", "json")
        report = json.loads(assessed.stdout)
        assert assessed.returncode == 1
        assert report["decision"] == "BLOCKED"
        assert any("Lead-only path" in reason for reason in report["reasons"])

    allowed = candidate(common=False)
    allowed["workstreams"][0]["write_paths"] = ["docs/api/"]
    spec = write_spec(tmp_path, allowed, "unrelated-docs.json")
    assessed = cli("assess_parallelism.py", spec, "--format", "json")
    assert assessed.returncode == 0
    assert json.loads(assessed.stdout)["decision"] == "PARALLEL_SAFE"
