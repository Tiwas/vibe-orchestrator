[CmdletBinding()]
param(
    [Alias("Host")]
    [string]$BindHost = $(if ($env:VIBE_ORCHESTRATOR_HOST) { $env:VIBE_ORCHESTRATOR_HOST } else { "127.0.0.1" }),

    [int]$Port = $(if ($env:VIBE_ORCHESTRATOR_PORT) { [int]$env:VIBE_ORCHESTRATOR_PORT } else { 8765 }),

    [Alias("TargetRepo")]
    [string]$Repo = $(if ($env:VIBE_ORCHESTRATOR_TARGET_REPO) { $env:VIBE_ORCHESTRATOR_TARGET_REPO } else { "" }),

    [switch]$NoPicker,

    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

$LaunchDir = (Get-Location).Path
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

function Select-TargetRepo {
    $Shell = $null
    try {
        $Shell = New-Object -ComObject Shell.Application
    }
    catch {
        $Shell = $null
    }

    if ($null -ne $Shell) {
        $Folder = $Shell.BrowseForFolder(0, "Select the repository folder Vibe Orchestrator should work on", 0, $LaunchDir)
        if ($null -eq $Folder) {
            throw "No target repository selected."
        }

        return $Folder.Self.Path
    }

    Add-Type -AssemblyName System.Windows.Forms

    $Dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $Dialog.Description = "Select the repository folder Vibe Orchestrator should work on"
    $Dialog.SelectedPath = $LaunchDir
    $Dialog.ShowNewFolderButton = $false

    $Result = $Dialog.ShowDialog()
    if ($Result -ne [System.Windows.Forms.DialogResult]::OK -or [string]::IsNullOrWhiteSpace($Dialog.SelectedPath)) {
        throw "No target repository selected."
    }

    return $Dialog.SelectedPath
}

function Resolve-TargetRepo {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        if ($NoPicker) {
            $Path = $LaunchDir
        }
        else {
            $Path = Select-TargetRepo
        }
    }

    if (-not [System.IO.Path]::IsPathRooted($Path)) {
        $Path = Join-Path $LaunchDir $Path
    }

    $ResolvedPath = (Resolve-Path -LiteralPath $Path).Path
    if (-not (Test-Path -LiteralPath $ResolvedPath -PathType Container)) {
        throw "Target repository folder does not exist: $Path"
    }

    return $ResolvedPath
}

$TargetRepoPath = Resolve-TargetRepo $Repo

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
    $env:VIBE_ORCHESTRATOR_TARGET_REPO = $TargetRepoPath

    Write-Host "Starting Vibe Orchestrator on http://${BindHost}:${Port}"
    Write-Host "Target repository: $TargetRepoPath"
    & $PythonExe -m vibe_orchestrator
}
finally {
    Pop-Location
}
