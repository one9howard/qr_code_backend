#!/usr/bin/env python3
"""Fail if critical pytest fixtures are unavailable in this environment."""

from __future__ import annotations

import re
import subprocess
import sys


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", "--fixtures", "-q"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = (result.stdout or "") + "\n" + (result.stderr or "")

    if result.returncode != 0:
        print("[Runner] Fixture discovery failed.")
        print(output.strip())
        return result.returncode or 1

    if not re.search(r"(?m)^mocker\s", output):
        print("[Runner] ERROR: Required pytest fixture 'mocker' not found.")
        return 1

    print("[Runner] Fixture check passed: mocker is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
