#requires -Version 5.1
<#
.SYNOPSIS
    Create the isolated, broker-FREE virtualenv for NovaTacticBot (REPAIR-011).

.DESCRIPTION
    NovaTacticBot is ADVISORY-ONLY. It must never run in an environment where a
    broker / order-execution library is importable. This script builds a local
    .venv from requirements.txt and then PROVES the environment is broker-free by
    asserting that ib_insync (and friends) cannot be imported. If any broker
    package is reachable, the script fails non-zero and the venv is unusable.

    It installs ONLY into the repo-local .venv. It never touches the global
    interpreter and never installs anything globally.

.EXAMPLE
    ./setup_venv.ps1
    ./setup_venv.ps1 -Python "C:\Python314\python.exe"
#>
[CmdletBinding()]
param(
    # Base interpreter used to create the venv. Defaults to whatever `python` resolves to.
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvDir  = Join-Path $RepoRoot ".venv"

Write-Host "== NovaTacticBot advisory venv setup (REPAIR-011) ==" -ForegroundColor Cyan
Write-Host "Repo:  $RepoRoot"
Write-Host "Venv:  $VenvDir"

# 1. Create the venv (idempotent — reuse if already present).
if (-not (Test-Path (Join-Path $VenvDir "pyvenv.cfg"))) {
    Write-Host "Creating virtualenv..."
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
} else {
    Write-Host "Reusing existing virtualenv."
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { throw "venv python not found at $VenvPython" }

# 2. Install ONLY this repo's pinned requirements into the venv.
Write-Host "Installing requirements (broker-free)..."
& $VenvPython -m pip install --upgrade pip | Out-Null
& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# 3. HARD PROOF: the advisory env must not be able to import any broker library.
Write-Host "Verifying broker-free guarantee..."
& $VenvPython (Join-Path $RepoRoot "tools\verify_broker_free.py")
if ($LASTEXITCODE -ne 0) { throw "GUARDRAIL: advisory venv is NOT broker-free -- aborting" }

Write-Host ""
Write-Host "Done. Run NovaTacticBot inside this venv, e.g.:" -ForegroundColor Green
Write-Host "    $VenvPython tools\run_tacticbot.py --nova-options-dir C:\NovaGPT\Apps\NovaBotV2Options"
Write-Host "    $VenvPython -m pytest -q"
