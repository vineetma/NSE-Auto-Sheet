<#
.SYNOPSIS
    Enable, disable, inspect or remove the local Task Scheduler backup for run_local.ps1.

.DESCRIPTION
    GitHub Actions is the primary schedule. This script manages an optional local
    backup task that runs scripts\run_local.ps1 Mon-Fri at the given local time,
    as the current user, only while that user is logged on (no stored password).
    A missed start (laptop off or asleep) runs as soon as possible afterwards.

    enable   Create or replace the task and enable it.
    disable  Create or replace the task and leave it disabled (Run still works on demand).
    status   Show the task's state, last result and next run time (default).
    remove   Delete the task.

.PARAMETER Command
    enable | disable | status | remove. Default: status.

.PARAMETER TaskName
    Task name in Task Scheduler. Default: "NSE Auto Sheet".

.PARAMETER At
    Local start time, HH:mm (24h). Default: 20:00.

.PARAMETER WakeToRun
    Wake the computer from sleep to run the task.

.EXAMPLE
    .\scripts\local_schedule.ps1 enable
    .\scripts\local_schedule.ps1 enable -At 18:30 -WakeToRun
    .\scripts\local_schedule.ps1 disable
    .\scripts\local_schedule.ps1
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('enable', 'disable', 'status', 'remove')]
    [string]$Command = 'status',

    [string]$TaskName = 'NSE Auto Sheet',

    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$At = '20:00',

    [switch]$WakeToRun
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Wrapper  = Join-Path $RepoRoot 'scripts\run_local.ps1'

function Register-Task {
    if (-not (Test-Path $Wrapper)) { throw "Wrapper not found at $Wrapper" }

    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $Wrapper) `
        -WorkingDirectory $RepoRoot

    $trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
        -At ([datetime]::ParseExact($At, 'HH:mm', $null))

    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun:$WakeToRun `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force `
        -Description "Local backup for NSE-Auto-Sheet (GitHub Actions is primary). Logs: $RepoRoot\logs" | Out-Null
}

function Show-Status {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { Write-Output "'$TaskName' is not registered."; return }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    $next = if ($task.State -eq 'Disabled') { '(disabled)' } else { $info.NextRunTime }
    Write-Output ("'{0}': {1}. Last run: {2} (result {3}). Next run: {4}" -f
        $TaskName, $task.State, $info.LastRunTime, $info.LastTaskResult, $next)
}

switch ($Command) {
    'enable'  { Register-Task; Enable-ScheduledTask -TaskName $TaskName | Out-Null; Show-Status }
    'disable' { Register-Task; Disable-ScheduledTask -TaskName $TaskName | Out-Null; Show-Status }
    'status'  { Show-Status }
    'remove'  {
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Output "Removed '$TaskName'."
        } else { Write-Output "'$TaskName' is not registered." }
    }
}
