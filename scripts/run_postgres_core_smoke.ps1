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

    Invoke-Checked { uv run manage-postgres-core-schema --apply }
    Invoke-Checked { uv run manage-postgres-core-schema --apply }

    Assert-Equal "core schema exists" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'zsxq_core';") `
        "1"
    Assert-Equal "public schema absent" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'zsxq_public';") `
        "0"

    @'
import os
import psycopg2

conn = psycopg2.connect(os.environ["ZSXQ_POSTGRES_DSN"])
try:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO zsxq_core.groups (group_id, name, type) VALUES (1, 'Smoke Group', 'paid')")
        cur.execute("INSERT INTO zsxq_core.topics (group_id, topic_id, title, type, create_time) VALUES (1, 100, 'Smoke Topic', 'talk', '2026-05-07T10:00:00')")
        cur.execute("CREATE SCHEMA zsxq_public")
        cur.execute("CREATE VIEW zsxq_public.topics AS SELECT topic_id FROM zsxq_core.topics")
        cur.execute("CREATE SCHEMA zsxq_legacy_topics")
        cur.execute("CREATE TABLE zsxq_legacy_topics.topics (topic_id bigint primary key)")
        cur.execute("INSERT INTO zsxq_legacy_topics.topics VALUES (100)")
        cur.execute("CREATE TABLE zsxq_core.record_sources (record_table text, record_key text, source_schema text, source_row_id text, migrated_at timestamptz)")
        cur.execute("INSERT INTO zsxq_core.record_sources VALUES ('topics', '100', 'zsxq_legacy_topics', '100', CURRENT_TIMESTAMP)")
        cur.execute("ALTER TABLE zsxq_core.topics ADD COLUMN source_schema text")
        cur.execute("ALTER TABLE zsxq_core.topics ADD COLUMN source_row_id text")
        cur.execute("ALTER TABLE zsxq_core.topics ADD COLUMN migrated_at timestamptz")
    conn.commit()
finally:
    conn.close()
'@ | uv run python -

    $cleanupPlan = (uv run cleanup-postgres-legacy-artifacts --dry-run) -join "`n"
    if ($cleanupPlan -notmatch 'DROP SCHEMA IF EXISTS "zsxq_public" CASCADE;') {
        throw "cleanup dry-run did not include zsxq_public drop"
    }
    if ($cleanupPlan -notmatch 'DROP SCHEMA IF EXISTS "zsxq_legacy_topics" CASCADE;') {
        throw "cleanup dry-run did not include legacy schema drop"
    }
    if ($cleanupPlan -notmatch 'DROP TABLE IF EXISTS "zsxq_core"."record_sources" CASCADE;') {
        throw "cleanup dry-run did not include record_sources drop"
    }
    if ($cleanupPlan -notmatch 'DROP COLUMN IF EXISTS "source_schema"') {
        throw "cleanup dry-run did not include source_schema drop"
    }
    Write-Host "[ok] cleanup dry-run lists public, legacy, record_sources, and tracking columns"

    Invoke-Checked { uv run manage-postgres-core-access --apply --login-roles --reader-password $ReaderPassword --writer-password $WriterPassword }
    Invoke-Checked { uv run verify-postgres-reader-access --dsn "postgresql://zsxq_reader:$ReaderPassword@127.0.0.1:$Port/$Database" }
    Invoke-Checked { uv run verify-postgres-writer-access --dsn "postgresql://zsxq_writer:$WriterPassword@127.0.0.1:$Port/$Database" }

    docker exec -e "PGPASSWORD=$ReaderPassword" $ContainerName `
        psql -h 127.0.0.1 -U zsxq_reader -d $Database -v ON_ERROR_STOP=1 -tAc "INSERT INTO zsxq_core.groups (group_id) VALUES (2);" *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "zsxq_reader unexpectedly inserted into zsxq_core"
    }
    Write-Host "[ok] reader cannot insert into zsxq_core"

    Write-Host "PostgreSQL core smoke passed."
}
finally {
    $env:ZSXQ_DATABASE_BACKEND = $oldBackend
    $env:ZSXQ_POSTGRES_DSN = $oldDsn

    if (-not $KeepContainer) {
        docker rm -f $ContainerName *> $null
    }
}
