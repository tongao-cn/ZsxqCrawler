from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from backend.core.account_context import get_cookie_for_group
from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader
from backend.storage.db_compat import connect


DEFAULT_EXTENSIONS = (
    "pdf",
    "doc",
    "docx",
    "ppt",
    "pptx",
    "txt",
    "md",
    "csv",
    "tsv",
    "xls",
    "xlsx",
    "json",
    "xml",
    "yaml",
    "yml",
    "html",
    "htm",
    "rtf",
)


def _query_group_id(group_id: str) -> Any:
    value = str(group_id or "").strip()
    return int(value) if value.isdigit() else value


def _file_extension(name: str) -> str:
    return Path(str(name or "").strip()).suffix.lower().lstrip(".")


def _format_size(size: int) -> str:
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{int(size or 0)}B"


def _parse_extensions(value: str | None) -> set[str]:
    if not value:
        return set(DEFAULT_EXTENSIONS)
    return {item.strip().lower().lstrip(".") for item in value.split(",") if item.strip()}


def _load_candidate_rows(
    *,
    group_id: str,
    start_date: str,
    end_date: str,
    status: str,
    extensions: set[str],
    max_files: int | None,
) -> list[dict[str, Any]]:
    conditions = [
        "group_id = ?",
        "substr(create_time, 1, 10) >= ?",
        "substr(create_time, 1, 10) <= ?",
    ]
    params: list[Any] = [_query_group_id(group_id), start_date, end_date]
    if status != "all":
        conditions.append("download_status = ?")
        params.append(status)

    query = f"""
        SELECT file_id, name, COALESCE(size, 0), COALESCE(download_count, 0), create_time, download_status
        FROM files
        WHERE {' AND '.join(conditions)}
        ORDER BY create_time DESC, file_id DESC
    """
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    finally:
        conn.close()

    candidates: list[dict[str, Any]] = []
    for file_id, name, size, download_count, create_time, download_status in rows:
        ext = _file_extension(str(name or ""))
        if ext not in extensions:
            continue
        candidates.append(
            {
                "file_id": int(file_id),
                "name": str(name or f"file_{file_id}"),
                "size": int(size or 0),
                "download_count": int(download_count or 0),
                "create_time": str(create_time or ""),
                "download_status": str(download_status or ""),
                "extension": ext,
            }
        )
        if max_files is not None and len(candidates) >= max_files:
            break
    return candidates


def _write_manifest(rows: Sequence[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=(
                "file_id",
                "name",
                "extension",
                "size",
                "download_count",
                "create_time",
                "download_status",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


def _download_rows(
    *,
    group_id: str,
    rows: Iterable[dict[str, Any]],
    download_interval: float,
    long_sleep_interval: float,
    files_per_batch: int,
) -> dict[str, int]:
    cookie = get_cookie_for_group(group_id)
    downloader = ZSXQFileDownloader(
        cookie=cookie,
        group_id=group_id,
        download_interval=download_interval,
        long_sleep_interval=long_sleep_interval,
        files_per_batch=files_per_batch,
    )
    try:
        stats = {"total_files": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        rows_list = list(rows)
        stats["total_files"] = len(rows_list)
        for index, row in enumerate(rows_list, 1):
            print(f"[{index}/{len(rows_list)}] {row['name']}", flush=True)
            result = downloader.download_file(
                {
                    "file": {
                        "id": row["file_id"],
                        "name": row["name"],
                        "size": row["size"],
                        "download_count": row["download_count"],
                    }
                }
            )
            if result == "skipped":
                stats["skipped"] += 1
            elif result:
                stats["downloaded"] += 1
            else:
                stats["failed"] += 1
        return stats
    finally:
        downloader.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download analysis-friendly ZSXQ files by group, date range, and extension.")
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--start-date", required=True, help="Inclusive date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive date, YYYY-MM-DD.")
    parser.add_argument("--status", default="pending", choices=("pending", "failed", "all"))
    parser.add_argument("--extensions", help="Comma-separated extension allowlist. Defaults to analysis-friendly types.")
    parser.add_argument("--max-files", type=int, help="Limit after date/status/extension filtering.")
    parser.add_argument("--dry-run", action="store_true", help="Only write the manifest and print totals.")
    parser.add_argument("--download-interval", type=float, default=1.0)
    parser.add_argument("--long-sleep-interval", type=float, default=60.0)
    parser.add_argument("--files-per-batch", type=int, default=10)
    parser.add_argument("--manifest", type=Path, help="CSV manifest path.")
    args = parser.parse_args()

    extensions = _parse_extensions(args.extensions)
    rows = _load_candidate_rows(
        group_id=args.group_id,
        start_date=args.start_date,
        end_date=args.end_date,
        status=args.status,
        extensions=extensions,
        max_files=args.max_files,
    )
    total_size = sum(row["size"] for row in rows)
    default_manifest = Path("output") / "exports" / "file-download-candidates" / datetime.now().strftime("%Y%m%d_%H%M%S") / "manifest.csv"
    manifest_path = args.manifest or default_manifest
    _write_manifest(rows, manifest_path)

    print(f"group_id={args.group_id}")
    print(f"date_range={args.start_date}..{args.end_date}")
    print(f"extensions={','.join(sorted(extensions))}")
    print(f"candidate_files={len(rows)}")
    print(f"candidate_size={_format_size(total_size)}")
    print(f"manifest={manifest_path}")

    if args.dry_run:
        print("dry_run=true")
        return 0

    stats = _download_rows(
        group_id=args.group_id,
        rows=rows,
        download_interval=args.download_interval,
        long_sleep_interval=args.long_sleep_interval,
        files_per_batch=args.files_per_batch,
    )
    print(f"downloaded={stats['downloaded']}")
    print(f"skipped={stats['skipped']}")
    print(f"failed={stats['failed']}")
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
