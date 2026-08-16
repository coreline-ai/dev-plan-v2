from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from parallel_plan_lib import render_plan
from test_check_parallel_scope import git, repository
from test_parallel_dev_plan import create_plan


LESSON_ID = "DL-20260815T120000Z-a1b2c3d4"
NEW_LESSON_ID = "DL-20260815T120001Z-b1b2c3d4"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_lesson_tool(tmp_path: Path) -> Path:
    script = tmp_path / "dev_lesson.py"
    script.write_text(
        """import json, sys
from pathlib import Path
command = sys.argv[1]
if command == 'capabilities':
    print(json.dumps({
        'status': 'LESSON_TOOL_AVAILABLE',
        'capability_schema': 'dev-lesson-tool/v1',
        'lesson_schema': 'dev-lesson/v1',
        'commands': ['find', 'record', 'validate'],
        'features': ['repo_path', 'v2_evidence', 'advisory_only'],
    }))
elif command == 'validate':
    lesson = Path(sys.argv[2])
    root = Path(sys.argv[sys.argv.index('--root') + 1])
    if not lesson.is_file() or not lesson.read_text(encoding='utf-8').startswith('validated fixture '):
        raise SystemExit(2)
    print(json.dumps({
        'status': 'LESSON_VALID', 'count': 1,
        'lessons': [{'id': lesson.stem, 'repo_path': lesson.relative_to(root).as_posix()}],
        'warnings': [],
    }))
else:
    raise SystemExit(2)
""",
        encoding="utf-8",
    )
    return script


def write_lessons(repo: Path) -> None:
    lesson_dir = repo / "docs/dev-lessons"
    lesson_dir.mkdir(parents=True, exist_ok=True)
    for lesson_id in (LESSON_ID, NEW_LESSON_ID):
        (lesson_dir / f"{lesson_id}.md").write_text(f"validated fixture {lesson_id}\n", encoding="utf-8")


def record(cli, ledger: Path, unit: str, repo: Path, commit: str, command: str, *extra: object):
    return cli(
        "execution_ledger.py", "record-unit", ledger,
        "--scope-unit", unit, "--repo", repo, "--commit", commit,
        "--test-result", json.dumps({"command": command, "exit_code": 0}),
        "--qa", "PASS", "--reviewer", "independent",
        *extra, "--format", "json",
    )


def completed_execution(
    tmp_path: Path,
    cli,
    *,
    include_prior_reference: bool = True,
) -> tuple[Path, Path, Path, Path]:
    repo, _ = repository(tmp_path)
    (repo / ".gitignore").write_text("dev-plan/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-m", "ignore plans")
    baseline = git(repo, "rev-parse", "HEAD")
    plan = create_plan(repo, cli, common=False)
    for candidate_spec in repo.glob("candidate-*.json"):
        candidate_spec.unlink()
    payload = json.loads(plan.read_text(encoding="utf-8"))
    if include_prior_reference:
        payload["references"].append(f"docs/dev-lessons/{LESSON_ID}.md")
    plan.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan.with_suffix(".md").write_text(render_plan(payload, plan.with_suffix(".md").name), encoding="utf-8")
    ledger = plan.with_suffix(".execution.json")
    created = cli(
        "execution_ledger.py", "init", "--plan", plan, "--output", ledger,
        "--repo", repo, "--baseline", baseline, "--format", "json",
    )
    assert created.returncode == 0, created.stderr

    api_worktree, web_worktree = tmp_path / "lane-api", tmp_path / "lane-web"
    git(repo, "worktree", "add", "-b", "lane-api", str(api_worktree), baseline)
    git(repo, "worktree", "add", "-b", "lane-web", str(web_worktree), baseline)
    (api_worktree / "src/api/base.py").write_text("API = 2\n", encoding="utf-8")
    git(api_worktree, "add", "src/api/base.py")
    git(api_worktree, "commit", "-m", "api lane")
    api_commit = git(api_worktree, "rev-parse", "HEAD")
    assert record(cli, ledger, "WS-01", api_worktree, api_commit, "pytest tests/api").returncode == 0
    (web_worktree / "src/web/base.py").write_text("WEB = 2\n", encoding="utf-8")
    git(web_worktree, "add", "src/web/base.py")
    git(web_worktree, "commit", "-m", "web lane")
    web_commit = git(web_worktree, "rev-parse", "HEAD")
    assert record(cli, ledger, "WS-02", web_worktree, web_commit, "pytest tests/web").returncode == 0
    git(repo, "merge", "--no-ff", "lane-api", "-m", "merge api lane")
    git(repo, "merge", "--no-ff", "lane-web", "-m", "merge web lane")
    integration_baseline = git(repo, "rev-parse", "HEAD")
    integrated = record(
        cli, ledger, "INTEGRATION", repo, integration_baseline, "pytest",
        "--scope-baseline", integration_baseline,
    )
    assert integrated.returncode == 0, integrated.stderr
    write_lessons(repo)
    return repo, plan, ledger, fake_lesson_tool(tmp_path)


def valid_input() -> dict[str, object]:
    return {
        "lesson_tool": {"status": "AVAILABLE", "detail": "dev-plan-generator/dev_lesson.py compatible"},
        "prior_lessons": [{
            "lesson_id": LESSON_ID,
            "disposition": "adopted",
            "reason": "API scope overlaps the prior failure mode.",
            "control": "Run the isolation regression test.",
            "task_refs": ["WS-01 task: add scoped key"],
            "test_refs": ["pytest tests/api"],
            "waiver": None,
        }],
        "occurrences": [{
            "occurrence_id": "OCC-001",
            "source_units": ["WS-01"],
            "summary": "Synthetic boundary mismatch.",
            "impact": "One lane required rework.",
            "evidence": "Tracked regression test and scope report.",
            "temporary_action": "Returned the change to WS-01.",
            "disposition": "new-lesson",
            "reason": "The prevention control is reusable.",
            "lesson_id": NEW_LESSON_ID,
            "durable_refs": ["tests/api/test_scope.py", "commit:0123456789abcdef"],
        }],
    }


def write_input(tmp_path: Path, value: dict[str, object]) -> Path:
    path = tmp_path / "outcomes-input.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def create(cli, plan: Path, ledger: Path, input_path: Path, tool: Path | None):
    args: list[object] = [
        "execution_outcomes.py", "create", "--plan", plan, "--ledger", ledger,
        "--input", input_path, "--format", "json",
    ]
    if tool is not None:
        args.extend(["--lesson-tool-script", tool])
    return cli(*args)


def test_outcomes_preserve_sources_and_verify_real_lesson_files(tmp_path: Path, cli) -> None:
    repo, plan, ledger, tool = completed_execution(tmp_path, cli)
    markdown = plan.with_suffix(".md")
    before = (plan.read_bytes(), markdown.read_bytes(), ledger.read_bytes())
    created = create(cli, plan, ledger, write_input(tmp_path, valid_input()), tool)
    assert created.returncode == 0, created.stderr
    outcomes = plan.with_suffix(".outcomes.json")
    assert before == (plan.read_bytes(), markdown.read_bytes(), ledger.read_bytes())
    payload = json.loads(outcomes.read_text(encoding="utf-8"))
    assert {item["lesson_id"] for item in payload["verified_lessons"]} == {LESSON_ID, NEW_LESSON_ID}
    validated = cli(
        "execution_outcomes.py", "validate", outcomes,
        "--lesson-tool-script", tool, "--format", "json",
    )
    assert validated.returncode == 0, validated.stderr
    (repo / f"docs/dev-lessons/{NEW_LESSON_ID}.md").write_text("tampered\n", encoding="utf-8")
    invalid = cli(
        "execution_outcomes.py", "validate", outcomes,
        "--lesson-tool-script", tool, "--format", "json",
    )
    assert invalid.returncode == 2
    assert "changed or is missing" in json.loads(invalid.stdout)["error"]


def test_record_pending_requires_unavailable_tool(tmp_path: Path, cli) -> None:
    _, plan, ledger, tool = completed_execution(tmp_path, cli)
    value = valid_input()
    value["prior_lessons"] = []
    occurrence = value["occurrences"][0]
    occurrence["disposition"] = "record-pending"
    occurrence["lesson_id"] = None
    failed = create(cli, plan, ledger, write_input(tmp_path, value), tool)
    assert failed.returncode == 2
    assert "LESSON_TOOL_UNAVAILABLE" in json.loads(failed.stdout)["error"]
    value["lesson_tool"] = {"status": "LESSON_TOOL_UNAVAILABLE", "detail": "V1 common tool is not installed"}
    created = create(cli, plan, ledger, write_input(tmp_path, value), None)
    assert created.returncode == 0, created.stderr


def test_available_lesson_tool_requires_an_explicit_script(tmp_path: Path, cli) -> None:
    _, plan, ledger, _ = completed_execution(tmp_path, cli)
    result = create(cli, plan, ledger, write_input(tmp_path, valid_input()), None)
    assert result.returncode == 2
    assert "AVAILABLE requires --lesson-tool-script" in json.loads(result.stdout)["error"]


def test_prior_lesson_must_be_frozen_in_plan_references(tmp_path: Path, cli) -> None:
    _, plan, ledger, tool = completed_execution(tmp_path, cli, include_prior_reference=False)
    result = create(cli, plan, ledger, write_input(tmp_path, valid_input()), tool)
    assert result.returncode == 2
    assert "present in plan references" in json.loads(result.stdout)["error"]


def test_outcomes_reject_sensitive_data_and_invalid_adoption(tmp_path: Path, cli) -> None:
    _, plan, ledger, tool = completed_execution(tmp_path, cli)
    value = valid_input()
    value["occurrences"][0]["evidence"] = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz"
    result = create(cli, plan, ledger, write_input(tmp_path, value), tool)
    assert result.returncode == 2
    assert "sensitive" in json.loads(result.stdout)["error"]
    value = valid_input()
    value["prior_lessons"][0]["task_refs"] = []
    result = create(cli, plan, ledger, write_input(tmp_path, value), tool)
    assert result.returncode == 2
    assert "task_refs" in json.loads(result.stdout)["error"]


def test_outcomes_reject_fake_complete_ledger_and_missing_lesson(tmp_path: Path, cli) -> None:
    repo, plan, ledger, tool = completed_execution(tmp_path, cli)
    original = json.loads(ledger.read_text(encoding="utf-8"))
    ledger.write_text(json.dumps({
        "schema": "parallel-dev-execution/v1",
        "plan_id": original["plan_id"],
        "plan_path": str(plan),
        "plan_sha256": sha256(plan),
        "units": {unit: {"state": "passed"} for unit in ("WS-01", "WS-02", "INTEGRATION")},
    }), encoding="utf-8")
    result = create(cli, plan, ledger, write_input(tmp_path, valid_input()), tool)
    assert result.returncode == 2
    assert "fields mismatch" in json.loads(result.stdout)["error"]
    ledger.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (repo / f"docs/dev-lessons/{NEW_LESSON_ID}.md").unlink()
    result = create(cli, plan, ledger, write_input(tmp_path, valid_input()), tool)
    assert result.returncode == 2
    assert "does not exist" in json.loads(result.stdout)["error"]


def test_outcomes_recalculate_scope_from_committed_git_evidence(tmp_path: Path, cli) -> None:
    _, plan, ledger, tool = completed_execution(tmp_path, cli)
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["units"]["WS-01"]["scope_files"][0]["path"] = "src/web/base.py"
    ledger.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = create(cli, plan, ledger, write_input(tmp_path, valid_input()), tool)
    assert result.returncode == 2
    assert "scope files differ from committed Git evidence" in json.loads(result.stdout)["error"]


def test_outcomes_validate_reruns_v1_after_sidecar_hash_tamper(tmp_path: Path, cli) -> None:
    repo, plan, ledger, tool = completed_execution(tmp_path, cli)
    created = create(cli, plan, ledger, write_input(tmp_path, valid_input()), tool)
    assert created.returncode == 0, created.stderr
    outcomes = plan.with_suffix(".outcomes.json")
    lesson = repo / f"docs/dev-lessons/{NEW_LESSON_ID}.md"
    lesson.write_text("not a valid lesson\n", encoding="utf-8")
    payload = json.loads(outcomes.read_text(encoding="utf-8"))
    for item in payload["verified_lessons"]:
        if item["lesson_id"] == NEW_LESSON_ID:
            item["sha256"] = sha256(lesson)
    outcomes.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    invalid = cli(
        "execution_outcomes.py", "validate", outcomes,
        "--lesson-tool-script", tool, "--format", "json",
    )
    assert invalid.returncode == 2
    assert "failed V1 validation" in json.loads(invalid.stdout)["error"]


def test_outcomes_refuse_overwrite_without_removing_existing_file(tmp_path: Path, cli) -> None:
    _, plan, ledger, tool = completed_execution(tmp_path, cli)
    output = plan.with_suffix(".outcomes.json")
    output.write_text("original\n", encoding="utf-8")
    result = create(cli, plan, ledger, write_input(tmp_path, valid_input()), tool)
    assert result.returncode == 2
    assert output.read_text(encoding="utf-8") == "original\n"
