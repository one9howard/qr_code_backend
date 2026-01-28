# scripts/check_specs_sync.py
from __future__ import annotations

import sys
from pathlib import Path

# Fix import path for running from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_specs_md import generate_specs_md

SPECS_MD = REPO_ROOT / "SPECS.md"

def main() -> int:
    if not SPECS_MD.exists():
        print("FAIL: SPECS.md not found.")
        return 2

    current = SPECS_MD.read_text(encoding="utf-8").replace("\r\n", "\n")
    expected = generate_specs_md().replace("\r\n", "\n")

    if current != expected:
        print("FAIL: SPECS.md is out of sync with services/specs.py")
        print("Fix: run `python scripts/generate_specs_md.py` and commit the result.")
        return 1

    print("OK: SPECS.md matches services/specs.py (generated output).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
