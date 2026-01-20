#!/usr/bin/env python3
"""
Fail if pytest collects 0 tests.

Used in CI to ensure tests are actually discovered and run.

Usage:
    pytest --collect-only -q > /tmp/collect.txt
    python scripts/fail_if_no_tests.py /tmp/collect.txt
    
Or pipe directly:
    pytest --collect-only -q 2>&1 | python scripts/fail_if_no_tests.py -
"""
import sys
import re


def count_tests(output: str) -> int:
    """
    Parse pytest collect-only output and return test count.
    
    Handles formats like:
    - "5 tests collected"
    - "23 tests collected in 0.12s"
    - "<Session test_foo.py>" style listings
    """
    # Try to find "N tests collected" pattern
    match = re.search(r"(\d+)\s+tests?\s+collected", output)
    if match:
        return int(match.group(1))
    
    # Count individual test function lines (fallback)
    # Format: "tests/test_foo.py::test_bar"
    test_lines = [line for line in output.splitlines() 
                  if "::" in line and "test_" in line]
    return len(test_lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/fail_if_no_tests.py <collect_output_file>")
        print("   or: pytest --collect-only -q | python scripts/fail_if_no_tests.py -")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    if input_file == "-":
        output = sys.stdin.read()
    else:
        with open(input_file, "r", encoding="utf-8", errors="replace") as f:
            output = f.read()
    
    test_count = count_tests(output)
    
    print(f"Tests collected: {test_count}")
    
    if test_count == 0:
        print("❌ ERROR: No tests collected!")
        print("CI cannot pass with 0 tests - ensure tests/ directory has test files.")
        sys.exit(1)
    else:
        print(f"✓ Found {test_count} tests")
        sys.exit(0)


if __name__ == "__main__":
    main()
