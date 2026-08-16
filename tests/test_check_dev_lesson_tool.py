from __future__ import annotations

import json
from pathlib import Path


def fake_skill(tmp_path: Path, payload: dict[str, object]) -> Path:
    skill = tmp_path / "dev-plan-generator"
    script = skill / "scripts/dev_lesson.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "import json\n"
        f"print(json.dumps({payload!r}))\n",
        encoding="utf-8",
    )
    return skill


def capabilities() -> dict[str, object]:
    return {
        "status": "LESSON_TOOL_AVAILABLE",
        "capability_schema": "dev-lesson-tool/v1",
        "lesson_schema": "dev-lesson/v1",
        "commands": ["find", "record", "validate"],
        "features": ["repo_path", "v2_evidence", "advisory_only"],
    }


def test_compatible_v1_tool_is_ready(tmp_path: Path, cli) -> None:
    skill = fake_skill(tmp_path, capabilities())
    result = cli("check_dev_lesson_tool.py", "--skill-dir", skill, "--format", "json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "LESSON_TOOL_READY"


def test_missing_or_incompatible_v1_tool_is_explicit(tmp_path: Path, cli) -> None:
    missing = cli("check_dev_lesson_tool.py", "--skill-dir", tmp_path / "missing", "--format", "json")
    assert missing.returncode == 1
    assert json.loads(missing.stdout)["status"] == "LESSON_TOOL_UNAVAILABLE"

    payload = capabilities()
    payload["features"] = ["repo_path"]
    skill = fake_skill(tmp_path, payload)
    incompatible = cli("check_dev_lesson_tool.py", "--skill-dir", skill, "--format", "json")
    assert incompatible.returncode == 1
    report = json.loads(incompatible.stdout)
    assert report["status"] == "LESSON_TOOL_INCOMPATIBLE"
    assert any("missing features" in item for item in report["errors"])
