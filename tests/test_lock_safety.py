from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.plan_core import PlanError, PlanFileLock
from scripts.workspace_guard import GuardError, IntegrationLock


def test_integration_lock_is_exclusive_and_recovers_after_process_exit(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / ".codex-dev-plan-integration.lock"
    lock_path.write_text("{partial", encoding="utf-8")
    with IntegrationLock(tmp_path):
        with pytest.raises(GuardError):
            with IntegrationLock(tmp_path):
                pass

    script = (
        "import os,sys\n"
        "from pathlib import Path\n"
        "from scripts.workspace_guard import IntegrationLock\n"
        "IntegrationLock(Path(sys.argv[1])).__enter__()\n"
        "os._exit(0)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )
    assert completed.returncode == 0
    with IntegrationLock(tmp_path):
        assert json.loads(lock_path.read_text(encoding="utf-8"))["state"] == "HELD"
    assert json.loads(lock_path.read_text(encoding="utf-8"))["state"] == "RELEASED"


def test_plan_lock_uses_kernel_ownership_not_owner_json(tmp_path: Path) -> None:
    lock_path = tmp_path / "plan.md.lock"
    lock_path.write_text("", encoding="utf-8")
    with PlanFileLock(lock_path, timeout=0):
        with pytest.raises(PlanError) as caught:
            with PlanFileLock(lock_path, timeout=0):
                pass
        assert caught.value.code == "LOCK_TIMEOUT"
    with PlanFileLock(lock_path, timeout=0):
        assert json.loads(lock_path.read_text(encoding="utf-8"))["state"] == "HELD"
