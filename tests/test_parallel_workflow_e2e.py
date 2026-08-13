from __future__ import annotations

import json
from pathlib import Path

from test_check_parallel_scope import git, plan_root, repository, report
from test_parallel_dev_plan import create_plan


def record(cli, ledger: Path, unit: str, repo: Path, commit: str, command: str, *extra: object):
    return cli(
        "execution_ledger.py", "record-unit", ledger,
        "--scope-unit", unit, "--repo", repo, "--commit", commit,
        "--test-result", json.dumps({"command": command, "exit_code": 0}),
        "--qa", "PASS", "--reviewer", "independent",
        *extra, "--format", "json",
    )


def test_safe_parallel_worktree_flow_reaches_complete_ledger(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    root = plan_root(tmp_path)
    plan = create_plan(root, cli, common=False)
    ledger = root / "workflow.execution.json"
    assert cli(
        "execution_ledger.py", "init", "--plan", plan, "--output", ledger,
        "--repo", repo, "--baseline", baseline,
    ).returncode == 0

    api_worktree, web_worktree = tmp_path / "lane-api", tmp_path / "lane-web"
    git(repo, "worktree", "add", "-b", "lane-api", str(api_worktree), baseline)
    git(repo, "worktree", "add", "-b", "lane-web", str(web_worktree), baseline)

    (api_worktree / "src/api/base.py").write_text("API = 2\n", encoding="utf-8")
    git(api_worktree, "add", "src/api/base.py")
    git(api_worktree, "commit", "-m", "api lane")
    api_commit = git(api_worktree, "rev-parse", "HEAD")
    assert report(cli, plan, api_worktree, baseline, "WS-01")[1]["status"] == "SCOPE_OK"
    assert record(cli, ledger, "WS-01", api_worktree, api_commit, "pytest tests/api").returncode == 0

    (web_worktree / "src/web/base.py").write_text("WEB = 2\n", encoding="utf-8")
    git(web_worktree, "add", "src/web/base.py")
    git(web_worktree, "commit", "-m", "web lane")
    web_commit = git(web_worktree, "rev-parse", "HEAD")
    assert report(cli, plan, web_worktree, baseline, "WS-02")[1]["status"] == "SCOPE_OK"
    assert record(cli, ledger, "WS-02", web_worktree, web_commit, "pytest tests/web").returncode == 0

    git(repo, "merge", "--no-ff", "lane-api", "-m", "merge api lane")
    git(repo, "merge", "--no-ff", "lane-web", "-m", "merge web lane")
    integration_baseline = git(repo, "rev-parse", "HEAD")
    integrated = record(
        cli, ledger, "INTEGRATION", repo, integration_baseline, "pytest",
        "--scope-baseline", integration_baseline,
    )
    assert integrated.returncode == 0, integrated.stderr
    final = cli("execution_ledger.py", "status", ledger, "--verify-git", "--format", "json")
    assert final.returncode == 0
    assert json.loads(final.stdout)["status"] == "EXECUTION_COMPLETE"
