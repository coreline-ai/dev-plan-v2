#!/usr/bin/env python3
"""Check runtime dependencies without attempting installation."""

from __future__ import annotations

import importlib.metadata
import json
import sys

try:
    import fcntl  # noqa: F401
except ImportError:
    fcntl = None  # type: ignore[assignment]


REQUIREMENTS = {
    "PyYAML": (6, 0, 2),
    "markdown-it-py": (4, 0, 0),
}


def version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in value.split("."):
        digits = "".join(character for character in part if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def main() -> int:
    report: dict[str, object] = {
        "python": sys.version.split()[0],
        "python_ok": sys.version_info >= (3, 11),
        "posix_flock_ok": fcntl is not None,
        "dependencies": {},
    }
    valid = bool(report["python_ok"]) and bool(report["posix_flock_ok"])
    dependencies: dict[str, object] = {}
    for distribution, minimum in REQUIREMENTS.items():
        try:
            version = importlib.metadata.version(distribution)
            okay = version_tuple(version) >= minimum
            dependencies[distribution] = {"installed": True, "version": version, "valid": okay}
            valid = valid and okay
        except importlib.metadata.PackageNotFoundError:
            dependencies[distribution] = {"installed": False, "valid": False}
            valid = False
    report["dependencies"] = dependencies
    report["valid"] = valid
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not valid:
        print(
            'Install into an isolated environment with: '
            'python3.11 -m pip install "PyYAML>=6.0.2,<7" "markdown-it-py>=4,<5"',
            file=sys.stderr,
        )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
