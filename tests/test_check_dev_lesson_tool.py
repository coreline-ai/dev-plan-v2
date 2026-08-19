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


def installed_skill(root: Path, directory: str, name: str, payload: dict[str, object] | None = None, marker: str = "") -> Path:
    skill = root / directory
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test {marker}\n---\n\n# Test\n",
        encoding="utf-8",
    )
    if payload is not None:
        script = skill / "scripts/dev_lesson.py"
        script.parent.mkdir(parents=True)
        script.write_text("import json\n" f"print(json.dumps({payload!r}))\n", encoding="utf-8")
    return skill


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


def test_install_layout_is_ready_with_one_canonical_v1_and_v2(tmp_path: Path, cli) -> None:
    root = tmp_path / "skills"
    installed_skill(root, "dev-plan-generator", "dev-plan-generator", capabilities())
    installed_skill(root, "parallel-dev-plan-orchestrator", "parallel-dev-plan-orchestrator")

    result = cli("check_dev_lesson_tool.py", "--check-install-layout", "--skills-root", root, "--format", "json")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "PLAN_SKILL_INSTALL_READY"
    assert report["lesson_tool"]["status"] == "LESSON_TOOL_READY"
    assert {item["name"] for item in report["installations"]} == {
        "dev-plan-generator",
        "parallel-dev-plan-orchestrator",
    }


def test_install_layout_distinguishes_missing_v1_v2_and_incompatible_v1(tmp_path: Path, cli) -> None:
    only_v2 = tmp_path / "only-v2"
    installed_skill(only_v2, "parallel-dev-plan-orchestrator", "parallel-dev-plan-orchestrator")
    missing_v1 = cli("check_dev_lesson_tool.py", "--check-install-layout", "--skills-root", only_v2, "--format", "json")
    assert missing_v1.returncode == 1
    assert json.loads(missing_v1.stdout)["status"] == "PLAN_SKILL_V1_MISSING"

    only_v1 = tmp_path / "only-v1"
    installed_skill(only_v1, "dev-plan-generator", "dev-plan-generator", capabilities())
    missing_v2 = cli("check_dev_lesson_tool.py", "--check-install-layout", "--skills-root", only_v1, "--format", "json")
    assert missing_v2.returncode == 1
    assert json.loads(missing_v2.stdout)["status"] == "PLAN_SKILL_V2_MISSING"

    incompatible_root = tmp_path / "incompatible"
    bad = capabilities()
    bad["features"] = []
    installed_skill(incompatible_root, "dev-plan-generator", "dev-plan-generator", bad)
    installed_skill(incompatible_root, "parallel-dev-plan-orchestrator", "parallel-dev-plan-orchestrator")
    incompatible = cli("check_dev_lesson_tool.py", "--check-install-layout", "--skills-root", incompatible_root, "--format", "json")
    assert incompatible.returncode == 1
    assert json.loads(incompatible.stdout)["status"] == "PLAN_SKILL_V1_INCOMPATIBLE"


def test_duplicate_v2_name_reports_paths_and_hashes_without_modifying_files(tmp_path: Path, cli) -> None:
    root = tmp_path / "skills"
    installed_skill(root, "dev-plan-generator", "dev-plan-generator", capabilities())
    canonical = installed_skill(root, "parallel-dev-plan-orchestrator", "parallel-dev-plan-orchestrator", marker="canonical")
    stale = installed_skill(root, "dev-plan-v2", "parallel-dev-plan-orchestrator", marker="stale")
    before = {path: path.read_bytes() for path in (canonical / "SKILL.md", stale / "SKILL.md")}

    result = cli("check_dev_lesson_tool.py", "--check-install-layout", "--skills-root", root, "--format", "json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "DUPLICATE_SKILL_NAME"
    issue = next(item for item in report["issues"] if item["code"] == "DUPLICATE_SKILL_NAME")
    assert set(issue["paths"]) == {str(canonical), str(stale)}
    assert len(set(issue["hashes"])) == 2
    assert {path: path.read_bytes() for path in before} == before


def test_symlink_alias_is_deduplicated_but_escape_is_rejected(tmp_path: Path, cli) -> None:
    root = tmp_path / "skills"
    installed_skill(root, "dev-plan-generator", "dev-plan-generator", capabilities())
    canonical = installed_skill(root, "parallel-dev-plan-orchestrator", "parallel-dev-plan-orchestrator")
    (root / "dev-plan-v2").symlink_to(canonical, target_is_directory=True)

    alias = cli("check_dev_lesson_tool.py", "--check-install-layout", "--skills-root", root, "--format", "json")
    assert alias.returncode == 0, alias.stderr
    assert json.loads(alias.stdout)["status"] == "PLAN_SKILL_INSTALL_READY"

    outside = installed_skill(tmp_path / "outside", "v2", "parallel-dev-plan-orchestrator")
    (root / "escaped-v2").symlink_to(outside, target_is_directory=True)
    escaped = cli("check_dev_lesson_tool.py", "--check-install-layout", "--skills-root", root, "--format", "json")
    report = json.loads(escaped.stdout)
    assert escaped.returncode == 1
    assert report["status"] == "PLAN_SKILL_INSTALL_INVALID"
    assert any(item["code"] == "SKILL_PATH_ESCAPE" for item in report["issues"])


def test_install_layout_check_is_read_only(tmp_path: Path, cli) -> None:
    root = tmp_path / "skills"
    v1 = installed_skill(root, "dev-plan-generator", "dev-plan-generator", capabilities())
    v2 = installed_skill(root, "parallel-dev-plan-orchestrator", "parallel-dev-plan-orchestrator")
    watched = [v1 / "SKILL.md", v1 / "scripts/dev_lesson.py", v2 / "SKILL.md"]
    before = {path: (path.read_bytes(), path.stat().st_mode) for path in watched}
    for path in watched:
        path.chmod(0o444)
    v1.chmod(0o555)
    v2.chmod(0o555)

    try:
        result = cli("check_dev_lesson_tool.py", "--check-install-layout", "--skills-root", root, "--format", "json")
        assert result.returncode == 0, result.stderr
        for path, (content, _) in before.items():
            assert path.read_bytes() == content
            assert path.stat().st_mode & 0o222 == 0
    finally:
        v1.chmod(0o755)
        v2.chmod(0o755)
        for path, (_, mode) in before.items():
            path.chmod(mode & 0o777)
