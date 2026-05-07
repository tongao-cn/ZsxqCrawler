param(
    [string]$ContainerName = "zsxq-pg-core-smoke",
    [int]$Port = 55433,
    [string]$Image = "postgres:16-alpine",
    [string]$Database = "zsxq_core_smoke",
    [string]$PostgresPassword = "postgres",
    [string]$ReaderPassword = "readerpass",
    [string]$WriterPassword = "writerpass",
    [switch]$KeepContainer
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$oldBackend = $env:ZSXQ_DATABASE_BACKEND
$oldDsn = $env:ZSXQ_POSTGRES_DSN

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-PgSql {
    param(
        [string]$User,
        [string]$Password,
        [string]$Sql
    )
    $output = docker exec -e "PGPASSWORD=$Password" $ContainerName `
        psql -h 127.0.0.1 -U $User -d $Database -v ON_ERROR_STOP=1 -tAc $Sql
    if ($LASTEXITCODE -ne 0) {
        throw "psql failed for user $User"
    }
    return ($output | Out-String).Trim()
}

function Assert-Equal {
    param([string]$Name, [string]$Actual, [string]$Expected)
    if ($Actual -ne $Expected) {
        throw "$Name expected '$Expected' but got '$Actual'"
    }
    Write-Host "[ok] $Name = $Actual"
}

try {
    Set-Location $repoRoot

    $existing = docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
    if ($existing -eq $ContainerName) {
        docker rm -f $ContainerName | Out-Null
    }

    Invoke-Checked {
        docker run --name $ContainerName `
            -e "POSTGRES_PASSWORD=$PostgresPassword" `
            -e "POSTGRES_USER=postgres" `
            -e "POSTGRES_DB=$Database" `
            -p "${Port}:5432" `
            -d $Image | Out-Null
    }

    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        docker exec -e "PGPASSWORD=$PostgresPassword" $ContainerName `
            psql -h 127.0.0.1 -U postgres -d $Database -tAc "SELECT 1" *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        throw "PostgreSQL container did not become ready"
    }

    $env:ZSXQ_DATABASE_BACKEND = "postgres"
    $env:ZSXQ_POSTGRES_DSN = "postgresql://postgres:$PostgresPassword@127.0.0.1:$Port/$Database"

    @'
import os
import psycopg2

conn = psycopg2.connect(os.environ["ZSXQ_POSTGRES_DSN"])
try:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA zsxq_legacy_topics")
        cur.execute("CREATE SCHEMA zsxq_legacy_files")
        cur.execute("CREATE SCHEMA zsxq_legacy_tasks")
        cur.execute("CREATE SCHEMA zsxq_legacy_accounts")
        cur.execute("CREATE TABLE zsxq_legacy_topics.groups (group_id BIGINT PRIMARY KEY, name TEXT, type TEXT, background_url TEXT)")
        cur.execute("CREATE TABLE zsxq_legacy_topics.topics (group_id BIGINT, topic_id BIGINT PRIMARY KEY, title TEXT, type TEXT, create_time TEXT, updated_at TEXT, imported_at TEXT)")
        cur.execute("CREATE TABLE zsxq_legacy_topics.comments (comment_id BIGINT PRIMARY KEY, topic_id BIGINT, owner_user_id BIGINT, text TEXT, create_time TEXT)")
        cur.execute("INSERT INTO zsxq_legacy_topics.groups VALUES (1, 'Core Group', 'paid', 'https://example.test/bg.png')")
        cur.execute("INSERT INTO zsxq_legacy_topics.topics VALUES (1, 100, 'Core Topic', 'talk', '2026-05-07T10:00:00', '2026-05-07T11:00:00', '2026-05-07T11:01:00')")
        cur.execute("INSERT INTO zsxq_legacy_topics.comments VALUES (200, 100, 300, 'useful comment', '2026-05-07T10:05:00')")
        cur.execute("CREATE TABLE zsxq_legacy_files.files (file_id BIGINT PRIMARY KEY, name TEXT, size BIGINT, download_status TEXT, local_path TEXT, create_time TEXT, updated_at TEXT)")
        cur.execute("CREATE TABLE zsxq_legacy_files.file_ai_analyses (file_id BIGINT PRIMARY KEY, status TEXT, summary TEXT, content_type TEXT, source_path TEXT, updated_at TEXT)")
        cur.execute("INSERT INTO zsxq_legacy_files.files VALUES (400, 'report.pdf', 12345, 'downloaded', 'files/report.pdf', '2026-05-07T09:00:00', '2026-05-07T09:30:00')")
        cur.execute("INSERT INTO zsxq_legacy_files.file_ai_analyses VALUES (400, 'done', 'file summary', 'application/pdf', 'files/report.pdf', '2026-05-07T21:00:00')")
        cur.execute("CREATE TABLE zsxq_legacy_tasks.task_runs (task_id TEXT PRIMARY KEY, type TEXT, status TEXT, message TEXT, created_at TEXT, updated_at TEXT)")
        cur.execute("CREATE TABLE zsxq_legacy_tasks.task_logs (id BIGINT PRIMARY KEY, task_id TEXT, message TEXT, created_at TEXT)")
        cur.execute("INSERT INTO zsxq_legacy_tasks.task_runs VALUES ('task_1_1', 'crawl_latest', 'completed', 'done', '2026-05-07T08:00:00', '2026-05-07T08:01:00')")
        cur.execute("INSERT INTO zsxq_legacy_tasks.task_logs VALUES (1, 'task_1_1', 'log line', '2026-05-07T08:00:10')")
        cur.execute("CREATE TABLE zsxq_legacy_accounts.accounts (id TEXT PRIMARY KEY, name TEXT, cookie TEXT, created_at TEXT, updated_at TEXT)")
        cur.execute("INSERT INTO zsxq_legacy_accounts.accounts VALUES ('acc-1', 'Account', 'cookie', '2026-05-07T07:00:00', NULL)")
    conn.commit()
finally:
    conn.close()
'@ | uv run python -

    Invoke-Checked { uv run migrate-postgres-schemas-to-core --dry-run }
    Invoke-Checked { uv run migrate-postgres-schemas-to-core --apply }
    Invoke-Checked { uv run migrate-postgres-schemas-to-core --apply }
    Invoke-Checked { uv run migrate-postgres-schemas-to-core --verify-only }
    Invoke-Checked { uv run manage-postgres-public-schema --apply --build-indexes }
    Invoke-Checked { uv run manage-postgres-public-schema --apply --build-indexes }

    Assert-Equal "core topics rows" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_core.topics;") `
        "1"
    Assert-Equal "core files rows" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_core.files;") `
        "1"
    Assert-Equal "core task rows" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_core.task_runs;") `
        "1"
    Assert-Equal "public topics rows" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_public.topics;") `
        "1"
    Assert-Equal "public files rows" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_public.files;") `
        "1"
    Assert-Equal "legacy schemas retained" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'zsxq_legacy_%';") `
        "4"

    Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "ALTER ROLE zsxq_reader LOGIN PASSWORD '$ReaderPassword'; ALTER ROLE zsxq_writer LOGIN PASSWORD '$WriterPassword';" | Out-Null
    Invoke-Checked {
        uv run verify-postgres-reader-access --dsn "postgresql://zsxq_reader:$ReaderPassword@127.0.0.1:$Port/$Database"
    }
    Invoke-Checked {
        uv run verify-postgres-writer-access --dsn "postgresql://zsxq_writer:$WriterPassword@127.0.0.1:$Port/$Database"
    }

    docker exec -e "PGPASSWORD=$ReaderPassword" $ContainerName `
        psql -h 127.0.0.1 -U zsxq_reader -d $Database -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM zsxq_core.topics;" *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "zsxq_reader unexpectedly selected from zsxq_core"
    }
    Write-Host "[ok] reader cannot select zsxq_core"

    docker exec -e "PGPASSWORD=$ReaderPassword" $ContainerName `
        psql -h 127.0.0.1 -U zsxq_reader -d $Database -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM zsxq_legacy_topics.topics;" *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "zsxq_reader unexpectedly selected from legacy schema"
    }
    Write-Host "[ok] reader cannot select legacy schema"

    Write-Host "PostgreSQL core smoke passed."
}
finally {
    $env:ZSXQ_DATABASE_BACKEND = $oldBackend
    $env:ZSXQ_POSTGRES_DSN = $oldDsn

    if (-not $KeepContainer) {
        docker rm -f $ContainerName *> $null
    }
}
