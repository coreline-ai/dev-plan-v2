from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from test_check_parallel_scope import git, plan_root, repository
from test_parallel_dev_plan import create_plan


def test_preflight_requires_clean_repo_and_resolves_lane_baseline(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=False)
    ready = cli(
        "preflight_parallel_exec.py", "--repo", repo, "--plan", plan,
        "--baseline", baseline, "--format", "json",
    )
    assert ready.returncode == 0
    payload = json.loads(ready.stdout)
    assert payload["status"] == "PREFLIGHT_READY"
    assert payload["lane_baseline"] == baseline

    (repo / "src/api/base.py").write_text("dirty\n", encoding="utf-8")
    blocked = cli(
        "preflight_parallel_exec.py", "--repo", repo, "--plan", plan,
        "--baseline", baseline, "--format", "json",
    )
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["status"] == "PREFLIGHT_BLOCKED"


def test_preflight_common_first_uses_verified_common_commit(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=True)
    first = cli(
        "preflight_parallel_exec.py", "--repo", repo, "--plan", plan,
        "--baseline", baseline, "--format", "json",
    )
    assert json.loads(first.stdout)["status"] == "PREFLIGHT_READY_COMMON_ONLY"
    (repo / "src/contracts/error.py").write_text("ERROR = 2\n", encoding="utf-8")
    git(repo, "add", "src/contracts/error.py")
    git(repo, "commit", "-m", "common contract")
    common_commit = git(repo, "rev-parse", "HEAD")
    second = cli(
        "preflight_parallel_exec.py", "--repo", repo, "--plan", plan,
        "--baseline", baseline, "--common-commit", common_commit, "--format", "json",
    )
    payload = json.loads(second.stdout)
    assert second.returncode == 0
    assert payload["status"] == "PREFLIGHT_READY"
    assert payload["lane_baseline"] == common_commit


def test_preflight_explicitly_blocks_submodules(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    plan = create_plan(plan_root(tmp_path), cli, common=False)
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{baseline},vendor/submodule")
    git(repo, "commit", "-m", "add gitlink")
    current = git(repo, "rev-parse", "HEAD")
    result = cli(
        "preflight_parallel_exec.py", "--repo", repo, "--plan", plan,
        "--baseline", current, "--format", "json",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "PREFLIGHT_BLOCKED"
    assert "submodules" in payload["errors"][0]


def test_execution_ledger_records_evidence_and_verifies_git(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    root = plan_root(tmp_path)
    plan = create_plan(root, cli, common=False)
    ledger = root / "execution.json"
    created = cli(
        "execution_ledger.py", "init", "--plan", plan, "--output", ledger,
        "--repo", repo, "--baseline", baseline, "--format", "json",
    )
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["status"] == "LEDGER_CREATED"

    (repo / "src/api/base.py").write_text("API = 2\n", encoding="utf-8")
    git(repo, "add", "src/api/base.py")
    git(repo, "commit", "-m", "api lane")
    worker_commit = git(repo, "rev-parse", "HEAD")
    test_result = json.dumps({"command": "pytest tests/api", "exit_code": 0})
    recorded = cli(
        "execution_ledger.py", "record-unit", ledger,
        "--scope-unit", "WS-01", "--repo", repo, "--commit", worker_commit,
        "--test-result", test_result,
        "--qa", "PASS", "--reviewer", "independent", "--format", "json",
    )
    assert recorded.returncode == 0, recorded.stderr
    assert json.loads(recorded.stdout)["state"] == "passed"

    status = cli("execution_ledger.py", "status", ledger, "--verify-git", "--format", "json")
    payload = json.loads(status.stdout)
    assert payload["status"] == "EXECUTION_PENDING"
    assert payload["states"]["WS-01"] == "passed"
    (repo / "src/api/base.py").write_text("changed after evidence\n", encoding="utf-8")
    blocked = cli("execution_ledger.py", "status", ledger, "--verify-git", "--format", "json")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["status"] == "RESUME_BLOCKED"


def test_ledger_blocks_missing_tests_and_optional_model_compliance(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    root = plan_root(tmp_path)
    plan = create_plan(root, cli, "20260813_150001", common=False)
    payload = json.loads(plan.read_text(encoding="utf-8"))
    payload["compliance"]["require_actual_model"] = True
    plan.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep the rendered pair valid after changing compliance.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from parallel_plan_lib import render_plan
    plan.with_suffix(".md").write_text(render_plan(payload, plan.with_suffix(".md").name), encoding="utf-8")

    ledger = root / "compliance.execution.json"
    assert cli(
        "execution_ledger.py", "init", "--plan", plan, "--output", ledger,
        "--repo", repo, "--baseline", baseline,
    ).returncode == 0
    (repo / "src/api/base.py").write_text("API = 9\n", encoding="utf-8")
    git(repo, "add", "src/api/base.py")
    git(repo, "commit", "-m", "compliance lane")
    worker_commit = git(repo, "rev-parse", "HEAD")
    recorded = cli(
        "execution_ledger.py", "record-unit", ledger,
        "--scope-unit", "WS-01", "--repo", repo, "--commit", worker_commit,
        "--qa", "PASS", "--reviewer", "independent",
        "--requested-model", "model-a", "--actual-model", "model-b", "--format", "json",
    )
    assert recorded.returncode == 1
    assert json.loads(recorded.stdout)["state"] == "blocked"


def test_common_pass_sets_the_lane_baseline(tmp_path, cli) -> None:
    repo, baseline = repository(tmp_path)
    root = plan_root(tmp_path)
    plan = create_plan(root, cli, "20260813_150002", common=True)
    ledger = root / "common.execution.json"
    assert cli(
        "execution_ledger.py", "init", "--plan", plan, "--output", ledger,
        "--repo", repo, "--baseline", baseline,
    ).returncode == 0
    (repo / "src/contracts/error.py").write_text("ERROR = 7\n", encoding="utf-8")
    git(repo, "add", "src/contracts/error.py")
    git(repo, "commit", "-m", "verified common")
    common_commit = git(repo, "rev-parse", "HEAD")
    result = cli(
        "execution_ledger.py", "record-unit", ledger,
        "--scope-unit", "COMMON", "--repo", repo, "--commit", common_commit,
        "--test-result", json.dumps({"command": "pytest tests/contracts", "exit_code": 0}),
        "--qa", "PASS", "--reviewer", "independent", "--format", "json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    assert payload["common_commit"] == common_commit
    assert payload["lane_baseline"] == common_commit


def test_atomic_ledger_write_preserves_existing_file_on_replace_failure(tmp_path, monkeypatch) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from execution_ledger import atomic_write

    target = tmp_path / "ledger.json"
    target.write_text('{"original": true}\n', encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        atomic_write(target, {"new": True})
    assert target.read_text(encoding="utf-8") == '{"original": true}\n'
    assert list(tmp_path.iterdir()) == [target]
