param(
    [Parameter(Mandatory = $true)]
    [string]$GroupId,

    [string]$BackendUrl = "http://localhost:8508",
    [string]$Date = "",
    [int]$CommentsPerTopic = 8,
    [switch]$CrawlLatestFirst
)

$ErrorActionPreference = "Stop"

$body = @{
    commentsPerTopic = $CommentsPerTopic
}

if ($Date.Trim()) {
    $body.date = $Date.Trim()
}

$jsonBody = $body | ConvertTo-Json -Depth 5
$url = "$BackendUrl/api/analysis/daily/$GroupId"

if ($CrawlLatestFirst.IsPresent) {
    $body.crawlLatestFirst = $true
    $url = "$BackendUrl/api/analysis/daily/run-today/$GroupId"
}

Write-Host "Starting daily topic report: $url"
$response = Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json" -Body $jsonBody

Write-Host "Task created: $($response.task_id)"
Write-Host "Task logs: $BackendUrl/api/tasks/$($response.task_id)/logs"
