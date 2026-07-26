from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_package_contains_only_parallel_v2_runtime(tmp_path: Path, cli) -> None:
    result = cli("package_skill.py", "--source", ROOT, "--output", tmp_path, "--format", "json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    destination = Path(report["destination"])
    paths = {entry["path"] for entry in report["files"]}
    assert report["skill"] == "parallel-dev-plan-orchestrator"
    assert paths == {
        "SKILL.md",
        "agents/openai.yaml",
        "scripts/new_parallel_dev_plan.py",
        "scripts/validate_parallel_dev_plan.py",
        "scripts/check_parallel_scope.py",
        "references/parallel-plan-format.md",
        "references/parallel-execution-workflow.md",
    }
    assert not (destination / "scripts" / "new_dev_plan.py").exists()
    assert not (destination / "references" / "plan-format.md").exists()
