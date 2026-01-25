#!/bin/bash
set -e

# Ensure pip-tools is installed
if ! command -v pip-compile &> /dev/null; then
    echo "pip-compile not found. Installing pip-tools..."
    pip install pip-tools
fi

# Generate a temporary requirements file to check against current
pip-compile --resolver=backtracking --generate-hashes --strip-extras --output-file requirements.txt.check requirements.in

# Compare
if ! cmp -s requirements.txt requirements.txt.check; then
    echo "ERROR: requirements.txt is out of sync with requirements.in!"
    echo "Please run: pip-compile --resolver=backtracking --generate-hashes --strip-extras --output-file requirements.txt requirements.in"
    rm requirements.txt.check
    exit 1
fi

echo "Lockfile is in sync."
rm requirements.txt.check
exit 0
