param(
    [string]$ContainerName = "zsxq-pg-runtime-cutover-smoke",
    [int]$Port = 55434,
    [string]$Image = "postgres:16-alpine",
    [string]$Database = "zsxq_runtime_smoke",
    [string]$PostgresPassword = "postgres",
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
import tempfile
from pathlib import Path

import psycopg2

from backend.storage.account_info_db import AccountInfoDB
from backend.storage.accounts_sql_manager import AccountsSQLManager
from backend.storage.task_store import TaskStore
from backend.storage.zsxq_database import ZSXQDatabase
from backend.storage.zsxq_file_database import ZSXQFileDatabase

dsn = os.environ["ZSXQ_POSTGRES_DSN"]

topic_db = ZSXQDatabase("runtime_topics.db")
ok = topic_db.import_topic_data({
    "topic_id": 9001,
    "group": {"group_id": 7001, "name": "Runtime Group", "type": "paid", "background_url": "https://example.test/bg.png"},
    "type": "talk",
    "title": "Runtime Topic",
    "create_time": "2026-05-07T18:00:00",
    "talk": {
        "text": "runtime smoke",
        "owner": {"user_id": 8001, "name": "Owner"},
        "files": [{"file_id": 9101, "name": "topic-file.pdf", "size": 12, "create_time": "2026-05-07T18:00:01"}],
    },
    "show_comments": [{"comment_id": 9201, "text": "comment", "owner": {"user_id": 8002, "name": "Commenter"}, "create_time": "2026-05-07T18:02:00"}],
})
topic_db.conn.commit()
topic_db.close()
if not ok:
    raise RuntimeError("topic import failed")

file_db = ZSXQFileDatabase("runtime_files.db")
file_db.import_file_response({
    "succeeded": True,
    "resp_data": {
        "index": "runtime-index",
        "files": [{
            "file": {"file_id": 9301, "name": "runtime-file.pdf", "size": 123, "download_status": "pending", "create_time": "2026-05-07T18:03:00"},
            "topic": {
                "topic_id": 9302,
                "group": {"group_id": 7001, "name": "Runtime Group", "type": "paid"},
                "type": "talk",
                "title": "Runtime File Topic",
                "create_time": "2026-05-07T18:04:00",
                "talk": {"text": "file topic", "owner": {"user_id": 8003, "name": "File Owner"}},
            },
        }],
    },
})
file_db.upsert_file_ai_analysis(9301, status="completed", summary="summary", content_type="application/pdf")
file_db.close()

with tempfile.TemporaryDirectory() as tmp:
    task_store = TaskStore(Path(tmp) / "runtime_tasks.db")
    task_store.create_task("runtime_task_1", "runtime_smoke", "running", "started", metadata={"group_id": "7001"})
    task_store.add_log("runtime_task_1", "log line")

    account_db = AccountsSQLManager(str(Path(tmp) / "runtime_accounts.db"))
    account = account_db.add_account("cookie=value", name="Runtime Account")
    assigned, message = account_db.assign_group_account("7001", account["id"])
    account_db.close()
    if not assigned:
        raise RuntimeError(message)

    info_db = AccountInfoDB(str(Path(tmp) / "runtime_account_info.db"))
    info_db.upsert_self_info(account["id"], {"uid": "u-runtime", "name": "Runtime User"})
    info_db.close()

with psycopg2.connect(dsn) as conn:
    with conn.cursor() as cur:
        checks = {
            "topics": "SELECT COUNT(*) FROM zsxq_core.topics WHERE topic_id IN (9001, 9302)",
            "files": "SELECT COUNT(*) FROM zsxq_core.files WHERE file_id IN (9101, 9301)",
            "comments": "SELECT COUNT(*) FROM zsxq_core.comments WHERE comment_id = 9201",
            "file_ai_analyses": "SELECT COUNT(*) FROM zsxq_core.file_ai_analyses WHERE file_id = 9301",
            "task_runs": "SELECT COUNT(*) FROM zsxq_core.task_runs WHERE task_id = 'runtime_task_1'",
            "task_logs": "SELECT COUNT(*) FROM zsxq_core.task_logs WHERE task_id = 'runtime_task_1'",
            "accounts": "SELECT COUNT(*) FROM zsxq_core.accounts WHERE name = 'Runtime Account'",
            "accounts_self": "SELECT COUNT(*) FROM zsxq_core.accounts_self WHERE uid = 'u-runtime'",
            "group_account_map": "SELECT COUNT(*) FROM zsxq_core.group_account_map WHERE group_id = '7001'",
        }
        for name, sql in checks.items():
            cur.execute(sql)
            count = int(cur.fetchone()[0])
            if count <= 0:
                raise RuntimeError(f"{name} was not written to zsxq_core")
            print(f"[ok] {name}: {count}")
        cur.execute("""
            SELECT COUNT(*)
            FROM information_schema.schemata
            WHERE schema_name LIKE 'zsxq_%'
              AND schema_name NOT IN ('zsxq_core', 'zsxq_public')
        """)
        legacy_count = int(cur.fetchone()[0])
        if legacy_count != 0:
            raise RuntimeError(f"runtime created legacy schemas: {legacy_count}")
        print("[ok] no legacy schemas created")
'@ | uv run python -

    Invoke-Checked { uv run backfill-postgres-core-group-ids --apply }
    Invoke-Checked { uv run manage-postgres-public-schema --apply --build-indexes }

    Write-Host "PostgreSQL runtime cutover smoke passed."
}
finally {
    $env:ZSXQ_DATABASE_BACKEND = $oldBackend
    $env:ZSXQ_POSTGRES_DSN = $oldDsn

    if (-not $KeepContainer) {
        docker rm -f $ContainerName *> $null
    }
}
