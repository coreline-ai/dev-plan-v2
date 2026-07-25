from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(name: str, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *(str(item) for item in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture
def cli():
    return run_script
