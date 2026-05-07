param(
    [string]$ContainerName = "zsxq-pg-shared-smoke",
    [int]$Port = 55433,
    [string]$Image = "postgres:16-alpine",
    [string]$Database = "zsxq_shared_smoke",
    [string]$PostgresPassword = "postgres",
    [string]$ReaderPassword = "readerpass",
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
    param(
        [string]$Name,
        [string]$Actual,
        [string]$Expected
    )
    if ($Actual -ne $Expected) {
        throw "$Name expected '$Expected' but got '$Actual'"
    }
    Write-Host "[ok] $Name = $Actual"
}

function Assert-AtLeast {
    param(
        [string]$Name,
        [string]$Actual,
        [int]$Minimum
    )
    $actualValue = [int]$Actual
    if ($actualValue -lt $Minimum) {
        throw "$Name expected at least $Minimum but got $Actual"
    }
    Write-Host "[ok] $Name >= $Minimum"
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
        docker exec $ContainerName pg_isready -U postgres -d $Database | Out-Null
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

dsn = os.environ["ZSXQ_POSTGRES_DSN"]
conn = psycopg2.connect(dsn)
try:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA zsxq_smoke_full")
        cur.execute("CREATE SCHEMA zsxq_smoke_legacy")
        cur.execute("""
            CREATE TABLE zsxq_smoke_full.groups (
                group_id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                background_url TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE zsxq_smoke_full.topics (
                group_id TEXT,
                topic_id TEXT PRIMARY KEY,
                title TEXT,
                type TEXT,
                create_time TEXT,
                updated_at TEXT,
                imported_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE zsxq_smoke_full.comments (
                comment_id TEXT PRIMARY KEY,
                topic_id TEXT,
                owner_user_id TEXT,
                text TEXT,
                create_time TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE zsxq_smoke_full.files (
                file_id TEXT PRIMARY KEY,
                name TEXT,
                size BIGINT,
                download_status TEXT,
                local_path TEXT,
                create_time TEXT,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE zsxq_smoke_full.columns (
                group_id TEXT,
                column_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                topics_count BIGINT,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE zsxq_smoke_full.column_topics (
                group_id TEXT,
                column_id TEXT,
                topic_id TEXT,
                title TEXT,
                create_time TEXT,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE zsxq_smoke_full.daily_ai_reports (
                group_id TEXT,
                report_date TEXT,
                topic_count BIGINT,
                summary TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE zsxq_smoke_full.file_ai_analyses (
                file_id TEXT PRIMARY KEY,
                status TEXT,
                summary TEXT,
                content_type TEXT,
                source_path TEXT,
                updated_at TEXT
            )
        """)
        cur.execute("""
            INSERT INTO zsxq_smoke_full.groups VALUES
            ('g-full', 'Full Group', 'paid', 'https://example.test/bg.png')
        """)
        cur.execute("""
            INSERT INTO zsxq_smoke_full.topics VALUES
            ('g-full', 't-full', 'Full Topic', 'talk', '2026-05-07T10:00:00', '2026-05-07T11:00:00', '2026-05-07T11:01:00')
        """)
        cur.execute("""
            INSERT INTO zsxq_smoke_full.comments VALUES
            ('c-full', 't-full', 'u-1', 'useful comment', '2026-05-07T10:05:00')
        """)
        cur.execute("""
            INSERT INTO zsxq_smoke_full.files VALUES
            ('f-full', 'report.pdf', 12345, 'downloaded', 'files/report.pdf', '2026-05-07T09:00:00', '2026-05-07T09:30:00')
        """)
        cur.execute("""
            INSERT INTO zsxq_smoke_full.columns VALUES
            ('g-full', 'col-full', 'Research', 'curated topics', 1, '2026-05-07T12:00:00')
        """)
        cur.execute("""
            INSERT INTO zsxq_smoke_full.column_topics VALUES
            ('g-full', 'col-full', 't-full', 'Full Topic', '2026-05-07T10:00:00', '2026-05-07T12:01:00')
        """)
        cur.execute("""
            INSERT INTO zsxq_smoke_full.daily_ai_reports VALUES
            ('g-full', '2026-05-07', 1, 'daily summary', '2026-05-07T20:00:00', '2026-05-07T20:01:00')
        """)
        cur.execute("""
            INSERT INTO zsxq_smoke_full.file_ai_analyses VALUES
            ('f-full', 'done', 'file summary', 'application/pdf', 'files/report.pdf', '2026-05-07T21:00:00')
        """)
        cur.execute("CREATE TABLE zsxq_smoke_legacy.groups (group_id TEXT PRIMARY KEY, name TEXT)")
        cur.execute("CREATE TABLE zsxq_smoke_legacy.topics (group_id TEXT, topic_id TEXT PRIMARY KEY, title TEXT)")
        cur.execute("CREATE TABLE zsxq_smoke_legacy.files (file_id TEXT PRIMARY KEY, name TEXT)")
        cur.execute("INSERT INTO zsxq_smoke_legacy.groups VALUES ('g-legacy', 'Legacy Group')")
        cur.execute("INSERT INTO zsxq_smoke_legacy.topics VALUES ('g-legacy', 't-legacy', 'Legacy Topic')")
        cur.execute("INSERT INTO zsxq_smoke_legacy.files VALUES ('f-legacy', 'legacy.txt')")
    conn.commit()
finally:
    conn.close()
'@ | uv run python -

    Invoke-Checked {
        uv run manage-postgres-public-schema --apply --build-indexes
    }
    Invoke-Checked {
        uv run manage-postgres-public-schema --apply --build-indexes
    }

    Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "ALTER ROLE zsxq_reader LOGIN PASSWORD '$ReaderPassword';" | Out-Null
    Invoke-Checked {
        uv run verify-postgres-reader-access --dsn "postgresql://zsxq_reader:$ReaderPassword@127.0.0.1:$Port/$Database"
    }

    Assert-Equal "public view count" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM information_schema.views WHERE table_schema = 'zsxq_public';") `
        "8"
    Assert-Equal "topics rows" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_public.topics;") `
        "2"
    Assert-Equal "files rows" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_public.files;") `
        "2"
    Assert-Equal "groups rows" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_public.groups;") `
        "2"
    Assert-Equal "legacy optional fields become null" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_public.topics WHERE topic_id = 't-legacy' AND source_updated_at IS NULL AND topic_type IS NULL;") `
        "1"
    Assert-Equal "comment group_id filled from topics" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM zsxq_public.comments WHERE comment_id = 'c-full' AND group_id = 'g-full';") `
        "1"
    Assert-AtLeast "internal indexes created" `
        (Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT count(*) FROM pg_indexes WHERE schemaname LIKE 'zsxq_%' AND schemaname <> 'zsxq_public' AND indexname LIKE 'idx_topics_group_id_%';") `
        1
    Assert-Equal "reader can select public topics" `
        (Invoke-PgSql -User "zsxq_reader" -Password $ReaderPassword -Sql "SELECT count(*) FROM zsxq_public.topics;") `
        "2"

    $sourceSchema = Invoke-PgSql -User "postgres" -Password $PostgresPassword -Sql "SELECT source_schema FROM zsxq_public.topics LIMIT 1;"
    docker exec -e "PGPASSWORD=$ReaderPassword" $ContainerName `
        psql -h 127.0.0.1 -U zsxq_reader -d $Database -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM `"$sourceSchema`".topics;" *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "zsxq_reader unexpectedly selected from internal schema $sourceSchema"
    }
    Write-Host "[ok] reader cannot select internal schema"

    docker exec -e "PGPASSWORD=$ReaderPassword" $ContainerName `
        psql -h 127.0.0.1 -U zsxq_reader -d $Database -v ON_ERROR_STOP=1 -tAc "CREATE TABLE zsxq_public.reader_write_probe(id int);" *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "zsxq_reader unexpectedly created a table in zsxq_public"
    }
    Write-Host "[ok] reader cannot write to public schema"

    Write-Host "PostgreSQL shared smoke passed."
}
finally {
    $env:ZSXQ_DATABASE_BACKEND = $oldBackend
    $env:ZSXQ_POSTGRES_DSN = $oldDsn

    if (-not $KeepContainer) {
        docker rm -f $ContainerName *> $null
    }
}
