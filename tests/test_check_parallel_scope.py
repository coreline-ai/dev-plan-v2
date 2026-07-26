from __future__ import annotations

import json

from test_parallel_dev_plan import create_plan


def report(cli, plan, unit: str, *paths: str):
    args = ["check_parallel_scope.py", plan, "--scope-unit", unit, "--format", "json"]
    for path in paths:
        args.extend(("--changed-file", path))
    result = cli(*args)
    return result, json.loads(result.stdout)


def test_scope_checker_uses_one_worker_diff_and_rejects_cross_lane(tmp_path, cli) -> None:
    plan = create_plan(tmp_path, cli)
    result, payload = report(cli, plan, "WS-01", "src/api/errors.py", "tests/api/test_errors.py")
    assert result.returncode == 0
    assert payload["status"] == "SCOPE_OK"

    result, payload = report(cli, plan, "WS-01", "src/web/errors.py")
    assert result.returncode == 1
    assert payload["status"] == "SCOPE_VIOLATION"

    result, payload = report(cli, plan, "WS-01", "README.md")
    assert result.returncode == 1
    assert payload["status"] == "SCOPE_VIOLATION"


def test_scope_checker_handles_serial_units_rework_and_ambiguous_ownership(tmp_path, cli) -> None:
    plan = create_plan(tmp_path, cli, "20260726_160201")
    assert report(cli, plan, "COMMON", "pyproject.toml")[1]["status"] == "SCOPE_OK"
    assert report(cli, plan, "INTEGRATION", "tests/integration/test_all.py")[1]["status"] == "SCOPE_OK"
    assert report(cli, plan, "INTEGRATION", "src/api/errors.py")[1]["status"] == "SCOPE_VIOLATION"
    assert report(cli, plan, "REWORK-WS-01", "src/api/errors.py")[1]["status"] == "SCOPE_OK"

    text = plan.read_text(encoding="utf-8").replace("`src/api/`, `tests/api/`", "`src/`", 1)
    plan.write_text(text, encoding="utf-8")
    result, payload = report(cli, plan, "WS-02", "src/web/errors.py")
    assert result.returncode == 1
    assert payload["status"] == "SCOPE_AMBIGUOUS"


def test_scope_checker_has_no_aggregate_diff_option(tmp_path, cli) -> None:
    plan = create_plan(tmp_path, cli, "20260726_160202")
    result = cli("check_parallel_scope.py", plan, "--scope-unit", "WS-01", "--diff", "all-workers.diff")
    assert result.returncode == 2
