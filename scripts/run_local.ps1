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

.PARAMETER NoToast
    Don't show a Windows toast notification when the run fails.

.EXAMPLE
    .\scripts\run_local.ps1
    .\scripts\run_local.ps1 -RunDate 2026-10-01
#>
[CmdletBinding()]
param(
    [ValidatePattern('^(\d{4}-\d{2}-\d{2})?$')]
    [string]$RunDate = '',

    [string]$KeyPath = '',

    [switch]$NoToast
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

# Best effort: a failed toast must never change the run's result.
function Show-FailureToast([string]$Message) {
    try {
        $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        $null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
        $text = [Security.SecurityElement]::Escape($Message)
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>NSE Auto Sheet failed</text><text>$text</text></binding></visual></toast>")
        # Windows PowerShell's registered AppUserModelID, so the toast shows without registering our own app.
        $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show(
            [Windows.UI.Notifications.ToastNotification]::new($xml))
    }
    catch {
        Write-Log "WARNING: could not show failure toast: $($_.Exception.Message)"
    }
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
    $result = if ($exitCode -eq 0) { 'OK' } else { 'FAIL' }
    Write-Log ("RESULT: {0} (exit {1})" -f $result, $exitCode)
    Write-Log ("==== {0} run_local end (exit {1}) ====" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $exitCode)
}

if ($exitCode -ne 0 -and -not $NoToast) {
    Show-FailureToast ("Exit code {0}. See {1}" -f $exitCode, $LogFile)
}

exit $exitCode
