# One-time setup for RailMentes on Windows (PowerShell 5.1 or newer, no Docker).
#
# Usage (from anywhere):
#   .\scripts\dev_setup.ps1                  venv + packages + .env + data + trained model
#   .\scripts\dev_setup.ps1 -SkipData        skip data generation and training (app falls back to "delay stays as now")
#   .\scripts\dev_setup.ps1 -RunChecks       also run pytest, ruff, vitest, eslint and the frontend build
#
# Needs: Python 3.12 (python or py -3.12 on PATH) and Node.js 20+ with npm.
# If scripts are blocked:  Set-ExecutionPolicy -Scope Process Bypass
param(
    [switch]$SkipData,
    [switch]$RunChecks
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step([string]$text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail([string]$text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }
function Run([string]$what, [scriptblock]$command) {
    & $command
    if ($LASTEXITCODE -ne 0) { Fail "$what failed (exit code $LASTEXITCODE)." }
}

# ---- 1. find Python 3.12 and Node -----------------------------------------
Step "Checking Python 3.12 and Node.js"
$pythonCmd = $null
foreach ($candidate in @(@("py", "-3.12"), @("python"), @("python3"))) {
    if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
    $extra = @($candidate | Select-Object -Skip 1)
    $version = (& $candidate[0] @extra --version 2>&1 | Out-String).Trim()
    if ($version -match "^Python 3\.12\.") { $pythonCmd = $candidate; Write-Host "Found $version"; break }
}
if (-not $pythonCmd) { Fail "Python 3.12 not found. Install it from python.org and tick 'Add to PATH'." }

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Node.js not found. Install Node 20 or newer from nodejs.org." }
$nodeVersion = (node --version).Trim()
if ([int]($nodeVersion.TrimStart("v").Split(".")[0]) -lt 20) { Fail "Node $nodeVersion is too old; need 20 or newer." }
Write-Host "Found Node $nodeVersion"

# ---- 2. backend virtual environment and packages --------------------------
$venvPython = Join-Path $root "backend\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $venvVersion = (& $venvPython --version 2>&1 | Out-String).Trim()
    if ($venvVersion -notmatch "^Python 3\.12\.") {
        Fail "backend\.venv exists but is $venvVersion. Delete the folder backend\.venv yourself and run this script again."
    }
    Step "Reusing the existing backend\.venv ($venvVersion)"
} else {
    Step "Creating backend\.venv"
    $extra = @($pythonCmd | Select-Object -Skip 1)
    Run "Creating the virtual environment" { & $pythonCmd[0] @extra -m venv (Join-Path $root "backend\.venv") }
}

Step "Installing backend packages (a few minutes: LightGBM, SHAP and OR-Tools are large)"
Run "pip upgrade" { & $venvPython -m pip install --upgrade pip --quiet }
Push-Location (Join-Path $root "backend")
try { Run "pip install" { & $venvPython -m pip install -e ".[dev]" } } finally { Pop-Location }

# ---- 3. frontend packages --------------------------------------------------
Step "Installing frontend packages"
Push-Location (Join-Path $root "frontend")
try { Run "npm install" { npm install } } finally { Pop-Location }

# ---- 4. settings -----------------------------------------------------------
if (-not (Test-Path (Join-Path $root ".env"))) {
    Step "Creating .env from .env.example"
    Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
} else {
    Step ".env already exists, left unchanged"
}

# ---- 5. data and model -----------------------------------------------------
if ($SkipData) {
    Step "Skipping data and model (-SkipData). The app will predict 'delay stays as now' until you run scripts\train_model.py"
} else {
    Step "Generating the synthetic training data (180 simulated days, about 20 seconds)"
    Run "generate_data" { & $venvPython (Join-Path $root "scripts\generate_data.py") }
    Step "Training the delay model (about 15 seconds)"
    Run "train_model" { & $venvPython (Join-Path $root "scripts\train_model.py") }
}

# ---- 6. optional checks ----------------------------------------------------
if ($RunChecks) {
    Step "Backend: pytest"
    Push-Location (Join-Path $root "backend")
    try {
        Run "pytest" { & $venvPython -m pytest -q }
        Step "Backend: ruff"
        Run "ruff" { & $venvPython -m ruff check app tests }
    } finally { Pop-Location }
    Push-Location (Join-Path $root "frontend")
    try {
        Step "Frontend: vitest"
        Run "vitest" { npm test }
        Step "Frontend: eslint"
        Run "eslint" { npm run lint }
        Step "Frontend: tsc and build"
        Run "build" { npm run build }
    } finally { Pop-Location }
}

Write-Host "`nSetup finished. Start everything with:  .\start_all.bat   then open http://localhost:5173" -ForegroundColor Green
