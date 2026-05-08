from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.storage.db_compat import get_postgres_dsn


def list_postgres_activity(limit: int = 30) -> List[Dict[str, Any]]:
    """Return active/waiting sessions for the configured PostgreSQL database."""
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")

    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pid,
                    state,
                    wait_event_type,
                    wait_event,
                    EXTRACT(EPOCH FROM (now() - query_start)) AS query_age_seconds,
                    LEFT(regexp_replace(query, '\\s+', ' ', 'g'), 240) AS query
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                  AND (state <> 'idle' OR wait_event_type IS NOT NULL)
                ORDER BY query_start NULLS LAST
                LIMIT %s
                """,
                (max(1, limit),),
            )
            return [_activity_row_to_dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _activity_row_to_dict(row: Any) -> Dict[str, Optional[Any]]:
    return {
        "pid": row[0],
        "state": row[1],
        "wait_event_type": row[2],
        "wait_event": row[3],
        "query_age_seconds": float(row[4]) if row[4] is not None else None,
        "query": row[5],
    }
