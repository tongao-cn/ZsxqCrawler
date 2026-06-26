[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$GroupId,

    [int]$RetentionDays = 365,

    # Default: "Sunday"
    [System.DayOfWeek[]]$DaysOfWeek = @([System.DayOfWeek]::Sunday),

    [uint32]$WeeksInterval = 1,

    # Default: "03:30"
    [string]$At = "03:30",

    [string]$TaskName,

    [switch]$Apply
)

$ErrorActionPreference = "Stop"

if ($RetentionDays -lt 1) {
    throw "RetentionDays must be at least 1."
}

if ($WeeksInterval -lt 1) {
    throw "WeeksInterval must be at least 1."
}

try {
    $runAt = [datetime]::ParseExact($At, "HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
}
catch {
    throw 'At must use HH:mm format, for example "03:30".'
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$cleanupScript = Join-Path $repoRoot "scripts\run_retention_cleanup.py"
if (-not (Test-Path -LiteralPath $cleanupScript)) {
    throw "Cleanup script not found: $cleanupScript"
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
    throw "uv was not found on PATH. Install uv or register the task from a shell where uv is available."
}

if (-not $TaskName) {
    $TaskName = "ZsxqCrawler retention cleanup $GroupId"
}

function Quote-TaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    return '"' + $Value.Replace('"', '\"') + '"'
}

$taskArguments = @(
    "run",
    "python",
    $cleanupScript,
    "--group-id",
    $GroupId,
    "--retention-days",
    [string]$RetentionDays
)

if ($Apply) {
    $taskArguments += "--apply"
}

$argumentText = ($taskArguments | ForEach-Object { Quote-TaskArgument ([string]$_) }) -join " "
$action = New-ScheduledTaskAction -Execute $uvCommand.Source -Argument $argumentText -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DaysOfWeek -WeeksInterval $WeeksInterval -At $runAt
$settings = New-ScheduledTaskSettingsSet `
    -RunOnlyIfIdle `
    -IdleDuration (New-TimeSpan -Minutes 10) `
    -IdleWaitTimeout (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

$description = "Runs ZsxqCrawler retention cleanup for group $GroupId. Apply=$($Apply.IsPresent); RetentionDays=$RetentionDays."

if ($PSCmdlet.ShouldProcess($TaskName, "Register weekly idle-only retention cleanup task")) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $description `
        -Force | Out-Null

    Write-Output "registered_task=$TaskName"
    Write-Output "group_id=$GroupId"
    Write-Output "retention_days=$RetentionDays"
    Write-Output "schedule=weekly $($DaysOfWeek -join ',') $At"
    Write-Output "idle_only=true"
    Write-Output "apply=$($Apply.IsPresent)"
}
