from __future__ import annotations

import json
from pathlib import Path

from scripts.plan_core import parse_plan, validate_structural


def test_new_plan_is_structurally_valid_and_never_overwrites(
    tmp_path: Path,
    spec_file: Path,
    cli,
) -> None:
    result = cli(
        "new_dev_plan.py",
        "--root",
        tmp_path,
        "--spec",
        spec_file,
        "--timestamp",
        "20260725_120001",
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    plan = Path(report["path"])
    assert report["plan_status"] == "DRAFT"
    assert not validate_structural(parse_plan(plan))
    before = plan.read_bytes()

    collision = cli(
        "new_dev_plan.py",
        "--root",
        tmp_path,
        "--spec",
        spec_file,
        "--timestamp",
        "20260725_120001",
    )
    assert collision.returncode == 2
    assert "PLAN_COLLISION" in collision.stderr or "already exists" in collision.stderr
    assert plan.read_bytes() == before


def test_generated_command_digest_is_present(tmp_path: Path, spec_file: Path, cli) -> None:
    result = cli(
        "new_dev_plan.py",
        "--root",
        tmp_path,
        "--spec",
        spec_file,
        "--timestamp",
        "20260725_120002",
    )
    assert result.returncode == 0
    plan = tmp_path / "dev-plan" / "implement_20260725_120002.md"
    test = parse_plan(plan).entity("TEST-101")
    assert len(test.data["command_sha256"]) == 64
    assert test.data["argv"] == ["python3.11", "-m", "pytest"]
