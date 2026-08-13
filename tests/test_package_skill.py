from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_package_contains_only_parallel_v2_runtime(tmp_path: Path, cli) -> None:
    validator = tmp_path / "quick_validate.py"
    validator.write_text(
        "from pathlib import Path\nimport sys\n"
        "root = Path(sys.argv[1])\n"
        "raise SystemExit(0 if (root / 'SKILL.md').is_file() else 1)\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"
    result = cli(
        "package_skill.py", "--source", ROOT, "--output", output,
        "--quick-validator", validator, "--format", "json",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    destination = Path(report["destination"])
    paths = {entry["path"] for entry in report["files"]}
    assert report["skill"] == "parallel-dev-plan-orchestrator"
    assert paths == {
        "SKILL.md",
        "agents/openai.yaml",
        "scripts/parallel_plan_lib.py",
        "scripts/assess_parallelism.py",
        "scripts/new_parallel_dev_plan.py",
        "scripts/validate_parallel_dev_plan.py",
        "scripts/preflight_parallel_exec.py",
        "scripts/check_parallel_scope.py",
        "scripts/execution_ledger.py",
        "references/parallel-plan-format.md",
        "references/parallel-execution-workflow.md",
    }
    assert not (destination / "scripts" / "new_dev_plan.py").exists()
    assert not (destination / "references" / "plan-format.md").exists()
