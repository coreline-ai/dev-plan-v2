from __future__ import annotations

import json
from pathlib import Path

from test_parallel_dev_plan import candidate, create_plan, write_spec


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
