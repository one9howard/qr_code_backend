#!/usr/bin/env python3
import os
import sys
import re

# Directories to check (runtime code)
CHECK_DIRS = ["routes", "services"]

# Files to exclude (dev/debug scripts inside those dirs, if any)
EXCLUDE_FILES = []

def check_no_prints():
    """
    Scans routes/ and services/ for print() statements.
    Fails if any are found.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"Scanning for print() statements in: {', '.join(CHECK_DIRS)}...")
    
    violation_count = 0
    
    for relative_dir in CHECK_DIRS:
        abs_dir = os.path.join(project_root, relative_dir)
        if not os.path.exists(abs_dir):
            print(f"Warning: Directory not found: {abs_dir}")
            continue
            
        for root, _, files in os.walk(abs_dir):
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                if filename in EXCLUDE_FILES:
                    continue
                    
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, project_root)
                
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    
                for i, line in enumerate(lines):
                    # Simple check for print( at start of line or after whitespace
                    # Ignores commented out prints (# print)
                    stripped = line.strip()
                    if stripped.startswith("print(") or re.search(r"[^#]*\bprint\(", line):
                        # Double check it's not a comment like "# some code print("
                        # This regex is naive, but we want to be strict.
                        # Matches "print(" but filters out "# ... print("
                        
                        # Check strictly for print(
                        if "print(" in line:
                            # Split by # to ignore comments
                            parts = line.split("#", 1)
                            code_part = parts[0]
                            if "print(" in code_part:
                                print(f"  [FAIL] {rel_path}:{i+1}: {stripped}")
                                violation_count += 1

    if violation_count > 0:
        print(f"\n❌ Found {violation_count} print() statements in runtime code.")
        print("Please replace them with logging or remove them.")
        sys.exit(1)
    else:
        print("\n✅ No print() statements found in runtime code.")
        sys.exit(0)

if __name__ == "__main__":
    check_no_prints()
