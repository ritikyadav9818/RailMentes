# Starts the RailMentes API with uvicorn (PowerShell, from anywhere).
# Usage:  .\scripts\run_backend.ps1            (port 8000)
#         .\scripts\run_backend.ps1 -Port 9000 -Reload
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)

$backend = Join-Path $PSScriptRoot "..\backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Backend virtual environment not found. Follow README.md Setup first."
    exit 1
}

$uvicornArgs = @("-m", "uvicorn", "app.api.main:app", "--host", $BindHost, "--port", $Port)
if ($Reload) { $uvicornArgs += @("--reload", "--reload-dir", "app") }

Write-Host "API docs: http://${BindHost}:${Port}/docs"
Set-Location $backend
& $python @uvicornArgs
