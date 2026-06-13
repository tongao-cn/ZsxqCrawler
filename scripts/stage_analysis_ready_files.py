from __future__ import annotations

import argparse
import csv
import os
import shutil
from pathlib import Path
from typing import Any, Sequence

from backend.storage.db_compat import connect
from scripts.download_analysis_ready_files import DEFAULT_EXTENSIONS, _format_size, _parse_extensions, _query_group_id


def _file_extension(name: str) -> str:
    return Path(str(name or "").strip()).suffix.lower().lstrip(".")


def _month_folder(create_time: str) -> str:
    value = str(create_time or "").strip()
    if len(value) >= 7 and value[4] == "-":
        return value[:7]
    return "unknown-month"


def _target_path(root: Path, row: dict[str, Any]) -> Path:
    source_name = Path(str(row["source_path"])).name
    month_dir = root / _month_folder(str(row["create_time"]))
    candidate = month_dir / source_name
    if not candidate.exists():
        return candidate

    source_path = Path(str(row["source_path"]))
    try:
        if candidate.samefile(source_path):
            return candidate
    except OSError:
        pass

    stem = candidate.stem
    suffix = candidate.suffix
    return month_dir / f"{stem}__{row['file_id']}{suffix}"


def _load_rows(
    *,
    group_id: str,
    start_date: str,
    end_date: str,
    extensions: set[str],
) -> list[dict[str, Any]]:
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT file_id, name, COALESCE(size, 0), create_time, local_path
            FROM files
            WHERE group_id = ?
              AND download_status = 'completed'
              AND local_path IS NOT NULL
              AND substr(create_time, 1, 10) >= ?
              AND substr(create_time, 1, 10) <= ?
            ORDER BY create_time DESC, file_id DESC
            """,
            (_query_group_id(group_id), start_date, end_date),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    results: list[dict[str, Any]] = []
    for file_id, name, size, create_time, local_path in rows:
        ext = _file_extension(str(name or ""))
        if ext not in extensions:
            continue
        source_path = Path(str(local_path or ""))
        if not source_path.exists() or not source_path.is_file():
            continue
        results.append(
            {
                "file_id": int(file_id),
                "name": str(name or f"file_{file_id}"),
                "extension": ext,
                "size": int(size or 0),
                "create_time": str(create_time or ""),
                "source_path": str(source_path),
            }
        )
    return results


def _stage_file(source: Path, target: Path, mode: str) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size == source.stat().st_size:
        return "exists"
    if mode == "hardlink":
        if target.exists():
            target.unlink()
        os.link(source, target)
        return "linked"
    shutil.copy2(source, target)
    return "copied"


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
                "create_time",
                "source_path",
                "staged_path",
                "stage_status",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage completed analysis-friendly files into month folders for Drive upload.")
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--start-date", required=True, help="Inclusive date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive date, YYYY-MM-DD.")
    parser.add_argument("--extensions", help="Comma-separated extension allowlist. Defaults to analysis-friendly types.")
    parser.add_argument("--output-dir", type=Path, help="Staging root. Defaults under output/exports/google-drive-staging.")
    parser.add_argument("--mode", choices=("copy", "hardlink"), default="copy")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    extensions = _parse_extensions(args.extensions)
    output_dir = args.output_dir or (
        Path("output")
        / "exports"
        / "google-drive-staging"
        / args.group_id
        / f"{args.start_date[:4]}-analysis-ready"
    )
    manifest_path = args.manifest or output_dir / "manifest.csv"
    rows = _load_rows(
        group_id=args.group_id,
        start_date=args.start_date,
        end_date=args.end_date,
        extensions=extensions,
    )

    staged_rows: list[dict[str, Any]] = []
    stats = {"copied": 0, "linked": 0, "exists": 0, "dry_run": 0}
    for row in rows:
        target = _target_path(output_dir, row)
        stage_status = "dry_run"
        if args.dry_run:
            stats["dry_run"] += 1
        else:
            stage_status = _stage_file(Path(str(row["source_path"])), target, args.mode)
            stats[stage_status] += 1
        staged_rows.append({**row, "staged_path": str(target), "stage_status": stage_status})

    _write_manifest(staged_rows, manifest_path)
    print(f"group_id={args.group_id}")
    print(f"date_range={args.start_date}..{args.end_date}")
    print(f"extensions={','.join(sorted(extensions or set(DEFAULT_EXTENSIONS)))}")
    print(f"source_files={len(rows)}")
    print(f"source_size={_format_size(sum(row['size'] for row in rows))}")
    print(f"output_dir={output_dir}")
    print(f"manifest={manifest_path}")
    print(f"mode={args.mode}")
    for key in ("copied", "linked", "exists", "dry_run"):
        print(f"{key}={stats[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
