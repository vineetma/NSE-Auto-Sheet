<#
.SYNOPSIS
    Run update_sheet.py locally, equivalent to the GitHub Actions workflow.

.DESCRIPTION
    Loads the Google service account key into GCP_CREDENTIALS, optionally sets
    RUN_DATE, runs update_sheet.py with the venv Python, appends all output to
    logs\run-YYYYMMDD.log, and exits with Python's exit code.

.PARAMETER RunDate
    Optional date to fetch the bhavcopy for (YYYY-MM-DD). Blank means today.

.PARAMETER KeyPath
    Path to the service account key JSON. Defaults to $env:NSE_KEY_PATH, then
    gsheet-access-keys.json in the repo root.

.EXAMPLE
    .\scripts\run_local.ps1
    .\scripts\run_local.ps1 -RunDate 2026-10-01
#>
[CmdletBinding()]
param(
    [ValidatePattern('^(\d{4}-\d{2}-\d{2})?$')]
    [string]$RunDate = '',

    [string]$KeyPath = ''
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python   = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Script   = Join-Path $RepoRoot 'update_sheet.py'
$LogDir   = Join-Path $RepoRoot 'logs'
$LogFile  = Join-Path $LogDir ("run-{0}.log" -f (Get-Date -Format 'yyyyMMdd'))

if (-not $KeyPath) {
    $KeyPath = if ($env:NSE_KEY_PATH) { $env:NSE_KEY_PATH } else { Join-Path $RepoRoot 'gsheet-access-keys.json' }
}

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-Log([string]$Line) {
    Write-Output $Line
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
}

# Remember the caller's env so a dot-sourced or interactive run doesn't leave the key behind.
$saved = @{}
foreach ($name in 'GCP_CREDENTIALS', 'RUN_DATE', 'PYTHONUTF8', 'PYTHONUNBUFFERED') {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$savedConsoleEncoding = [Console]::OutputEncoding

$exitCode = 1
try {
    Write-Log ("==== {0} run_local start (RUN_DATE='{1}') ====" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $RunDate)

    if (-not (Test-Path $Python)) { throw "venv Python not found at $Python (run: python -m venv .venv)" }
    if (-not (Test-Path $KeyPath)) { throw "Key file not found at $KeyPath (set -KeyPath or NSE_KEY_PATH)" }

    $env:GCP_CREDENTIALS  = Get-Content -Path $KeyPath -Raw
    $env:RUN_DATE         = $RunDate
    $env:PYTHONUTF8       = '1'
    $env:PYTHONUNBUFFERED = '1'
    # Python writes UTF-8 to the pipe; decode it as UTF-8 rather than the console code page.
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8

    # Windows PowerShell 5.1 turns native stderr lines into error records; don't let them abort the run.
    $ErrorActionPreference = 'Continue'
    & $Python $Script 2>&1 | ForEach-Object { Write-Log "$_" }
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
}
catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    $exitCode = 1
}
finally {
    foreach ($name in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
    [Console]::OutputEncoding = $savedConsoleEncoding
    Write-Log ("==== {0} run_local end (exit {1}) ====" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $exitCode)
}

exit $exitCode
