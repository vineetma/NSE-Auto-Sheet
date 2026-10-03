<#
.SYNOPSIS
    Register (or update) the Windows Task Scheduler task that runs run_local.ps1 on weekdays.

.DESCRIPTION
    Creates a task that runs scripts\run_local.ps1 Mon-Fri at the given local time,
    as the current user, only while that user is logged on (no stored password).
    A missed start (laptop off or asleep) runs as soon as possible afterwards.
    Re-running this script replaces the existing task with the same name.

.PARAMETER TaskName
    Task name in Task Scheduler. Default: "NSE Auto Sheet".

.PARAMETER At
    Local start time, HH:mm (24h). Default: 20:00.

.PARAMETER WakeToRun
    Wake the computer from sleep to run the task.

.PARAMETER Disabled
    Register the task but leave it disabled (on-demand runs only).

.EXAMPLE
    .\scripts\register_task.ps1
    .\scripts\register_task.ps1 -At 18:30 -WakeToRun
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'NSE Auto Sheet',

    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$At = '20:00',

    [switch]$WakeToRun,

    [switch]$Disabled
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Wrapper  = Join-Path $RepoRoot 'scripts\run_local.ps1'
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

$task = Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description "Runs NSE-Auto-Sheet's run_local.ps1 on weekdays. Logs: $RepoRoot\logs"

if ($Disabled) { $task = Disable-ScheduledTask -TaskName $TaskName }

$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Output ("Registered '{0}' ({1}), weekdays at {2}. Next run: {3}" -f $TaskName, $task.State, $At, $info.NextRunTime)
