from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import requests

from backend.core.account_context import build_stealth_headers, get_cookie_for_group
from backend.storage.db_compat import get_postgres_dsn
from backend.storage.postgres_core_schema import CORE_SCHEMA, quote_identifier
from backend.storage.zsxq_database import ZSXQDatabase


@dataclass(frozen=True)
class ProbeCounts:
    legacy_schema_count: int
    core_topics: int
    core_files: int
    core_comments: int
    core_tasks: int


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _count(conn, sql: str, params: tuple[Any, ...] = ()) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return int(cur.fetchone()[0])


def capture_counts(conn) -> ProbeCounts:
    return ProbeCounts(
        legacy_schema_count=_count(
            conn,
            """
            SELECT COUNT(*)
            FROM information_schema.schemata
            WHERE schema_name LIKE %s
              AND schema_name NOT IN (%s, %s)
            """,
            ("zsxq_%", CORE_SCHEMA, "zsxq_public"),
        ),
        core_topics=_count(conn, f"SELECT COUNT(*) FROM {quote_identifier(CORE_SCHEMA)}.{quote_identifier('topics')}"),
        core_files=_count(conn, f"SELECT COUNT(*) FROM {quote_identifier(CORE_SCHEMA)}.{quote_identifier('files')}"),
        core_comments=_count(conn, f"SELECT COUNT(*) FROM {quote_identifier(CORE_SCHEMA)}.{quote_identifier('comments')}"),
        core_tasks=_count(conn, f"SELECT COUNT(*) FROM {quote_identifier(CORE_SCHEMA)}.{quote_identifier('task_runs')}"),
    )


def _log(verbose: bool, message: str) -> None:
    if verbose:
        print(message, flush=True)


def run_real_probe(group_id: str, *, count: int, apply: bool, verbose: bool = False) -> dict[str, Any]:
    _log(verbose, "resolving PostgreSQL DSN")
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is not configured")
    _log(verbose, "capturing before counts")
    conn = psycopg2.connect(dsn)
    try:
        before = capture_counts(conn)
    finally:
        conn.close()

    result: dict[str, Any] = {"mode": "dry-run", "crawl_result": None}
    if apply:
        _log(verbose, "resolving group cookie")
        cookie = get_cookie_for_group(group_id)
        if not cookie or cookie == "your_cookie_here":
            raise RuntimeError(f"No usable cookie configured for group {group_id}")
        url = f"https://api.zsxq.com/v2/groups/{group_id}/topics"
        _log(verbose, f"requesting latest topics from {url}")
        response = requests.get(
            url,
            headers=build_stealth_headers(cookie),
            params={"scope": "all", "count": str(count)},
            timeout=30,
        )
        response.raise_for_status()
        _log(verbose, "parsing topic response")
        payload = response.json()
        if not payload.get("succeeded"):
            result["crawl_result"] = {
                "api_succeeded": False,
                "code": payload.get("code"),
                "error": payload.get("error") or payload.get("message"),
                "new_topics": 0,
                "updated_topics": 0,
                "errors": 1,
            }
        else:
            _log(verbose, "opening topic storage")
            topic_db = ZSXQDatabase(group_id)
            try:
                _log(verbose, "storing topic payload")
                stats = {"api_succeeded": True, "new_topics": 0, "updated_topics": 0, "errors": 0}
                for topic in payload.get("resp_data", {}).get("topics", []):
                    topic_id = topic.get("topic_id")
                    topic_db.cursor.execute(
                        "SELECT 1 FROM topics WHERE topic_id = ? AND group_id = ? LIMIT 1",
                        (topic_id, group_id),
                    )
                    exists = topic_db.cursor.fetchone() is not None
                    if topic_db.import_topic_data(topic):
                        stats["updated_topics" if exists else "new_topics"] += 1
                    else:
                        stats["errors"] += 1
                topic_db.conn.commit()
                result["crawl_result"] = stats
            finally:
                topic_db.close()
        result["mode"] = "apply"

    _log(verbose, "capturing after counts")
    conn = psycopg2.connect(dsn)
    try:
        after = capture_counts(conn)
    finally:
        conn.close()

    return {
        "group_id": group_id,
        "count": count,
        "before": before,
        "after": after,
        **result,
    }


def _delta(before: ProbeCounts, after: ProbeCounts, field: str) -> int:
    return getattr(after, field) - getattr(before, field)


def write_report(probe: dict[str, Any]) -> Path:
    report_path = _project_root() / "docs" / "postgres_real_cutover_probe_report.md"
    before: ProbeCounts = probe["before"]
    after: ProbeCounts = probe["after"]
    fields = [
        "legacy_schema_count",
        "core_topics",
        "core_files",
        "core_comments",
        "core_tasks",
    ]
    lines = [
        "# PostgreSQL Real Cutover Probe Report",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Mode: `{probe['mode']}`",
        f"- Group ID: `{probe['group_id']}`",
        f"- Requested latest topic count: {probe['count']}",
        f"- Crawl result: `{probe['crawl_result']}`",
        "- Apply mode fetches only the latest topic-list API payload and intentionally skips extra comment pagination.",
        "",
        "## Counts",
        "",
        "| Metric | Before | After | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for field in fields:
        lines.append(f"| `{field}` | {getattr(before, field)} | {getattr(after, field)} | {_delta(before, after, field)} |")
    if _delta(before, after, "legacy_schema_count") == 0:
        lines.extend(["", "## Verification", "", "- Legacy schema count did not increase."])
    else:
        lines.extend(["", "## Verification", "", "- [warn] Legacy schema count changed."])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real PostgreSQL cutover probe against a configured group")
    parser.add_argument("--group-id", required=True, help="Group ID to probe.")
    parser.add_argument("--count", type=int, default=1, help="Latest topic count for --apply.")
    parser.add_argument("--apply", action="store_true", help="Fetch latest topics and write through runtime storage.")
    parser.add_argument("--verbose", action="store_true", help="Print probe stage progress.")
    args = parser.parse_args()

    probe = run_real_probe(args.group_id, count=max(1, args.count), apply=args.apply, verbose=args.verbose)
    report_path = write_report(probe)
    print(f"Wrote {report_path}")
    before = probe["before"]
    after = probe["after"]
    print(f"legacy_schema_count: before={before.legacy_schema_count} after={after.legacy_schema_count}")
    print(f"crawl_result: {probe['crawl_result']}")
    if before.legacy_schema_count != after.legacy_schema_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
