$ErrorActionPreference = "Stop"

# 0) Sanity: clean working tree (this is NOT optional)
if (git status --porcelain) { throw "Working tree is dirty. Commit or stash changes before releasing." }

# 1) Activate venv (adjust if yours differs)
if (!(Test-Path ".\.venv\Scripts\Activate.ps1")) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2) Regenerate SPECS.md (must match services/specs.py)
python scripts\generate_specs_md.py

# 3) Enforce SPECS.md is committed (no silent drift)
if (git diff --name-only -- SPECS.md) {
    throw "SPECS.md changed. Commit it, then re-run the release commands."
}

# 4) Clean gate checks (must pass)
python scripts\check_release_clean.py
python scripts\release_gate.py

# 5) Build ZIP from git (no __pycache__ ever)
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$zip = "insite_signs_release_$ts.zip"
git archive --format=zip --output $zip HEAD
Write-Host "Built $zip"

# 6) Verify the artifact itself (not your repo)
$tmp = Join-Path $env:TEMP "insite_release_$ts"
New-Item -ItemType Directory -Path $tmp | Out-Null
Expand-Archive -Path $zip -DestinationPath $tmp -Force

Push-Location $tmp
python scripts\check_release_clean.py
python scripts\release_gate.py
Pop-Location

Remove-Item -Recurse -Force $tmp
Write-Host "Artifact verified OK."