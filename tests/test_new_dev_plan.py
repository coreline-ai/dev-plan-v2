from __future__ import annotations

import json
from pathlib import Path


def test_creates_a_valid_plan_without_overwriting(tmp_path: Path, cli) -> None:
    result = cli(
        "new_dev_plan.py", "--root", tmp_path, "--purpose", "로그인 오류 수정",
        "--scope", "src/auth", "--phase", "오류 처리", "--timestamp", "20260726_120000", "--format", "json",
    )
    assert result.returncode == 0, result.stderr
    path = Path(json.loads(result.stdout)["path"])
    assert path.is_file()
    assert cli("validate_dev_plan.py", path).returncode == 0
    before = path.read_bytes()
    assert cli("new_dev_plan.py", "--root", tmp_path, "--purpose", "다시 생성", "--timestamp", "20260726_120000").returncode == 2
    assert path.read_bytes() == before


def test_plan_can_have_multiple_phases(tmp_path: Path, cli) -> None:
    result = cli(
        "new_dev_plan.py", "--root", tmp_path, "--purpose", "기능 추가", "--phase", "구현", "--phase", "테스트", "--format", "json",
    )
    assert result.returncode == 0
    text = Path(json.loads(result.stdout)["path"]).read_text(encoding="utf-8")
    assert "## Phase 1. 구현" in text
    assert "## Phase 2. 테스트" in text
