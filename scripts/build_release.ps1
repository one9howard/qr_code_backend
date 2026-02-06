# scripts/build_release.ps1
# Deterministic release builder: regenerates SPECS.md, runs gates, builds ZIP via git archive,
# and saves the ZIP to ./releases/

$ErrorActionPreference = "Stop"

# --- Paths ---
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $RepoRoot "releases"

Push-Location $RepoRoot

try {
    # --- 0) Sanity: require clean working tree ---
    $status = (git status --porcelain)
    if ($status) { throw "Working tree is dirty. Commit or stash changes before releasing." }

    # --- 1) Ensure venv exists ---
    $VenvDir = Join-Path $RepoRoot ".venv"
    $PyExe = Join-Path $VenvDir "Scripts\python.exe"
    $PipExe = Join-Path $VenvDir "Scripts\pip.exe"

    if (!(Test-Path $PyExe)) {
        python -m venv $VenvDir
    }

    # --- 2) Install dependencies (deterministic) ---
    & $PipExe install -r (Join-Path $RepoRoot "requirements.txt") | Out-Host

    # --- 3) Regenerate SPECS.md and enforce it's committed ---
    & $PyExe (Join-Path $RepoRoot "scripts\generate_specs_md.py") | Out-Host

    $specDiff = (git diff --name-only -- "SPECS.md")
    if ($specDiff) {
        throw "SPECS.md changed. Commit it (git add SPECS.md && git commit), then re-run build_release.ps1."
    }

    # --- 4) Release gate checks (must pass) ---
    & $PyExe (Join-Path $RepoRoot "scripts\check_release_clean.py") | Out-Host
    & $PyExe (Join-Path $RepoRoot "scripts\release_gate.py")       | Out-Host

    # --- 5) Build ZIP to releases/ (git-tracked files only) ---
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $zipName = "insite_signs_release_$ts.zip"
    $zipPath = Join-Path $ReleaseDir $zipName

    git archive --format=zip --output $zipPath HEAD
    Write-Host "Built: $zipPath"

    # --- 6) Verify the artifact itself (not your repo) ---
    $tmp = Join-Path $env:TEMP ("insite_release_" + $ts)
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    New-Item -ItemType Directory -Path $tmp | Out-Null

    Expand-Archive -Path $zipPath -DestinationPath $tmp -Force

    Push-Location $tmp
    try {
        & $PyExe "scripts\check_release_clean.py" | Out-Host
        & $PyExe "scripts\release_gate.py"       | Out-Host
    }
    finally {
        Pop-Location
    }

    Remove-Item -Recurse -Force $tmp

    Write-Host "Artifact verified OK."
    Write-Host "Release ZIP saved to: $zipPath"
}
finally {
    Pop-Location
}