from __future__ import annotations

from backend.services.postgres_activity import list_postgres_activity


def main() -> None:
    rows = list_postgres_activity()
    if not rows:
        print("No active or waiting PostgreSQL sessions.")
        return

    for row in rows:
        print(
            "pid={pid} state={state} wait={wait_event_type}/{wait_event} age={query_age_seconds:.1f}s query={query}".format(
                **{
                    **row,
                    "query_age_seconds": row.get("query_age_seconds") or 0.0,
                    "wait_event_type": row.get("wait_event_type") or "-",
                    "wait_event": row.get("wait_event") or "-",
                }
            )
        )


if __name__ == "__main__":
    main()
