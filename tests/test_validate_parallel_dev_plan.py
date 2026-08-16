from __future__ import annotations

import json
from pathlib import Path

from test_parallel_dev_plan import candidate, create_plan, write_spec


ROOT = Path(__file__).resolve().parents[1]


def test_assessment_reports_safe_common_and_serial_decisions(tmp_path: Path, cli) -> None:
    safe = write_spec(tmp_path, candidate(common=False), "safe.json")
    result = cli("assess_parallelism.py", safe, "--format", "json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "PARALLEL_SAFE"

    common = write_spec(tmp_path, candidate(common=True), "common.json")
    result = cli("assess_parallelism.py", common, "--format", "json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "COMMON_FIRST"

    serial_value = candidate(common=False)
    serial_value["workstreams"] = serial_value["workstreams"][:1]
    serial_value["integration"]["depends_on"] = ["WS-01"]
    serial = write_spec(tmp_path, serial_value, "serial.json")
    result = cli("assess_parallelism.py", serial, "--format", "json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["decision"] == "SERIAL_RECOMMENDED"


def test_assessment_rejects_write_overlap_and_missing_tests(tmp_path: Path, cli) -> None:
    value = candidate(common=False)
    value["workstreams"][1]["write_paths"] = ["src/api/"]
    value["workstreams"][0]["tests"] = []
    spec = write_spec(tmp_path, value)
    result = cli("assess_parallelism.py", spec, "--format", "json")
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["decision"] == "SERIAL_RECOMMENDED"
    assert any("overlaps" in reason for reason in report["reasons"])
    assert any("independent test" in reason for reason in report["reasons"])


def test_assessment_recommends_serial_when_parallel_benefit_is_not_explained(tmp_path: Path, cli) -> None:
    value = candidate(common=False)
    value["assessment_reasons"] = []
    spec = write_spec(tmp_path, value, "missing-benefit.json")
    result = cli("assess_parallelism.py", spec, "--format", "json")
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["decision"] == "SERIAL_RECOMMENDED"
    assert any("necessity, independence, and parallel benefit" in reason for reason in report["reasons"])


def test_assessment_recommends_serial_for_residual_coordination_risk(tmp_path: Path, cli) -> None:
    value = candidate(common=False)
    value["coordination_risks"] = ["통합 시 두 lane의 상태 모델을 함께 다시 수정해야 할 수 있다"]
    spec = write_spec(tmp_path, value, "residual-risk.json")
    result = cli("assess_parallelism.py", spec, "--format", "json")
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["decision"] == "SERIAL_RECOMMENDED"
    assert any("coordination risk" in reason for reason in report["reasons"])


def test_validator_rejects_json_markdown_drift(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli)
    markdown = plan.with_suffix(".md")
    markdown.write_text(markdown.read_text(encoding="utf-8") + "\nmanual drift\n", encoding="utf-8")
    result = cli("validate_parallel_dev_plan.py", plan, "--format", "json")
    assert result.returncode == 1
    assert "does not match" in result.stdout


def test_validator_rejects_plan_path_overlap_and_wrong_waves(tmp_path: Path, cli) -> None:
    plan = create_plan(tmp_path, cli, "20260813_130001", common=False)
    payload = json.loads(plan.read_text(encoding="utf-8"))
    payload["workstreams"][1]["write_paths"] = ["src/api/"]
    payload["waves"] = [{"number": 1, "units": ["WS-01"]}, {"number": 2, "units": ["INTEGRATION"]}]
    plan.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = cli("validate_parallel_dev_plan.py", plan, "--format", "json")
    assert result.returncode == 1
    assert "ownership overlaps" in result.stdout
    assert "waves do not match" in result.stdout


def test_noncanonical_paths_are_blocked(tmp_path: Path, cli) -> None:
    value = candidate(common=False)
    value["workstreams"][0]["write_paths"] = ["./src/api/"]
    spec = write_spec(tmp_path, value)
    result = cli("assess_parallelism.py", spec, "--format", "json")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["decision"] == "BLOCKED"


def test_unknown_candidate_fields_and_schema_are_blocked(tmp_path: Path, cli) -> None:
    value = candidate(common=False)
    value["unexpected"] = True
    spec = write_spec(tmp_path, value, "unknown.json")
    result = cli("assess_parallelism.py", spec, "--format", "json")
    assert json.loads(result.stdout)["decision"] == "BLOCKED"

    value = candidate(common=False)
    value["schema"] = "parallel-dev-candidate/v999"
    spec = write_spec(tmp_path, value, "schema.json")
    result = cli("assess_parallelism.py", spec, "--format", "json")
    assert json.loads(result.stdout)["decision"] == "BLOCKED"


def test_skill_contract_uses_three_gates_without_count_based_decomposition() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    plan_format = (ROOT / "references" / "parallel-plan-format.md").read_text(encoding="utf-8")
    workflow = (ROOT / "references" / "parallel-execution-workflow.md").read_text(encoding="utf-8")
    agent = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "필요성" in skill and "독립성" in skill and "실제 속도 이점" in skill
    assert "사용자 요청 항목 수와 Workstream 수는 비교하지 않는다" in skill
    assert "테스트·문서·QA" in skill
    assert "같은 ASSESS를 반복하지 않는다" in skill
    assert "assessment_reasons" in plan_format
    assert "COMMON 이후에도 남는 위험" in plan_format
    assert "V2 산출물 없이 V1 경로를 한 번 반환" in workflow
    assert "Do not compare request count with workstream count" in agent
