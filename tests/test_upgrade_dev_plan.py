from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.plan_core import parse_plan, validate_structural


ROOT = Path(__file__).resolve().parents[1]


def test_upgrade_preserves_source_and_records_digest(tmp_path: Path, cli) -> None:
    source = tmp_path / "legacy.md"
    source.write_bytes((ROOT / "tests" / "fixtures" / "v1-plan.md").read_bytes())
    before = source.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    result = cli(
        "upgrade_dev_plan.py",
        source,
        "--root",
        tmp_path,
        "--timestamp",
        "20260725_120005",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert source.read_bytes() == before
    plan = tmp_path / "dev-plan" / "implement_20260725_120005.md"
    doc = parse_plan(plan)
    assert not validate_structural(doc)
    assert doc.metadata["status"] == "DRAFT"
    assert doc.metadata["upgrade_source"]["sha256"] == digest
    assert "TODO" in plan.read_text(encoding="utf-8")
