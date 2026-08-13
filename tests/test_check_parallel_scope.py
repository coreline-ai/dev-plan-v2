from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_parallel_dev_plan import create_plan


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    for directory in ("src/api", "src/web", "src/contracts", "tests/api", "tests/web"):
        (repo / directory).mkdir(parents=True, exist_ok=True)
    (repo / "src/api/base.py").write_text("API = 1\n", encoding="utf-8")
    (repo / "src/web/base.py").write_text("WEB = 1\n", encoding="utf-8")
    (repo / "src/contracts/error.py").write_text("ERROR = 1\n", encoding="utf-8")
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "tests@example.com")
    git(repo, "config", "user.name", "Tests")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")
    return repo, git(repo, "rev-parse", "HEAD")


def plan_root(tmp_path: Path) -> Path:
    root = tmp_path / "plans"
    root.mkdir()
    return root


def report(cli, plan: Path, repo: Path, baseline: str, unit: str):
    result = cli(
        "check_parallel_scope.py",
        "--plan", plan,
        "--repo", repo,
        "--baseline", baseline,
        "--scope-unit", unit,
        "--format", "json",
    )
    return result, json.loads(result.stdout)


def test_scope_checker_collects_tracked_and_untracked_changes(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=False)
    (repo / "src/api/base.py").write_text("API = 2\n", encoding="utf-8")
    (repo / "tests/api/new_test.py").write_text("def test_api(): pass\n", encoding="utf-8")
    result, payload = report(cli, plan, repo, baseline, "WS-01")
    assert result.returncode == 0
    assert payload["status"] == "SCOPE_OK"
    assert {item["status"] for item in payload["files"]} == {"M", "??"}


def test_scope_checker_rejects_cross_lane_and_unowned_files(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=False)
    (repo / "src/web/base.py").write_text("WEB = 2\n", encoding="utf-8")
    (repo / "README.md").write_text("unowned\n", encoding="utf-8")
    result, payload = report(cli, plan, repo, baseline, "WS-01")
    assert result.returncode == 1
    assert payload["status"] == "SCOPE_VIOLATION"
    assert all(item["outcome"] == "violation" for item in payload["files"])


def test_scope_checker_checks_both_rename_paths(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=False)
    git(repo, "mv", "src/api/base.py", "src/web/moved.py")
    result, payload = report(cli, plan, repo, baseline, "WS-01")
    assert result.returncode == 1
    assert payload["status"] == "SCOPE_VIOLATION"
    rename = [item for item in payload["files"] if item["status"].startswith("R")]
    assert {item["role"] for item in rename} == {"old", "new"}
    assert next(item for item in rename if item["role"] == "old")["outcome"] == "ok"
    assert next(item for item in rename if item["role"] == "new")["outcome"] == "violation"


def test_scope_checker_reports_empty_and_supports_rework(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=False)
    result, payload = report(cli, plan, repo, baseline, "WS-01")
    assert result.returncode == 1
    assert payload["status"] == "SCOPE_EMPTY"
    (repo / "src/api/base.py").write_text("API = 3\n", encoding="utf-8")
    result, payload = report(cli, plan, repo, baseline, "REWORK-WS-01")
    assert result.returncode == 0
    assert payload["status"] == "SCOPE_OK"


def test_scope_checker_includes_deleted_files(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=False)
    (repo / "src/api/base.py").unlink()
    result, payload = report(cli, plan, repo, baseline, "WS-01")
    assert result.returncode == 0
    assert payload["status"] == "SCOPE_OK"
    assert payload["files"][0]["status"] == "D"


def test_scope_checker_handles_control_characters_via_nul_git_output(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=False)
    unusual = repo / "src/api/name\twith-tab.py"
    unusual.write_text("VALUE = 1\n", encoding="utf-8")
    result, payload = report(cli, plan, repo, baseline, "WS-01")
    assert result.returncode == 0
    assert payload["status"] == "SCOPE_OK"
    assert payload["files"][0]["path"] == "src/api/name\twith-tab.py"
