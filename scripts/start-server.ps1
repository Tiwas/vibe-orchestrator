[CmdletBinding()]
param(
    [Alias("Host")]
    [string]$BindHost = $(if ($env:VIBE_ORCHESTRATOR_HOST) { $env:VIBE_ORCHESTRATOR_HOST } else { "127.0.0.1" }),

    [int]$Port = $(if ($env:VIBE_ORCHESTRATOR_PORT) { [int]$env:VIBE_ORCHESTRATOR_PORT } else { 8765 }),

    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $RepoRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

function New-ProjectVenv {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $VenvDir
        return
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $VenvDir
        return
    }

    throw "Python was not found. Install Python 3.11+ and try again."
}

Push-Location $RepoRoot
try {
    if (-not (Test-Path $PythonExe)) {
        Write-Host "Creating virtual environment in $VenvDir"
        New-ProjectVenv
    }

    if (-not $NoInstall) {
        Write-Host "Installing Vibe Orchestrator into the local virtual environment"
        & $PythonExe -m pip install -e $RepoRoot
    }

    $env:VIBE_ORCHESTRATOR_HOST = $BindHost
    $env:VIBE_ORCHESTRATOR_PORT = [string]$Port

    Write-Host "Starting Vibe Orchestrator on http://${BindHost}:${Port}"
    & $PythonExe -m vibe_orchestrator
}
finally {
    Pop-Location
}
