from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_package_contains_only_runtime_allowlist(tmp_path: Path, cli) -> None:
    output = tmp_path / "dist"
    result = cli(
        "package_skill.py",
        "--source",
        ROOT,
        "--output",
        output,
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    destination = Path(report["destination"])
    assert (destination / "SKILL.md").is_file()
    assert (destination / "scripts" / "plan_core.py").is_file()
    assert not (destination / "scripts" / "package_skill.py").exists()
    assert not (destination / "docs").exists()
    assert not (destination / "tests").exists()
    assert "valid" in str(report["validation"]).lower()

    second = cli(
        "package_skill.py",
        "--source",
        ROOT,
        "--output",
        output,
    )
    assert second.returncode == 2
    assert destination.is_dir()

    other_output = tmp_path / "other-dist"
    other = cli(
        "package_skill.py",
        "--source",
        ROOT,
        "--output",
        other_output,
        "--format",
        "json",
    )
    assert other.returncode == 0, other.stdout + other.stderr
    first_manifest = output / "codex-dev-plan-orchestrator.manifest.json"
    second_manifest = other_output / "codex-dev-plan-orchestrator.manifest.json"
    assert first_manifest.read_bytes() == second_manifest.read_bytes()
