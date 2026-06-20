"""Check that known scratch artifacts are not written to the repo root."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ROOT_PATTERNS = ("tmp_stock_analysis_*",)


def find_forbidden_root_artifacts(
    project_root: Path | None = None,
    patterns: Iterable[str] = FORBIDDEN_ROOT_PATTERNS,
) -> list[Path]:
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(matches)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail if known scratch artifacts are in the repository root.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    matches = find_forbidden_root_artifacts(args.project_root)
    if not matches:
        print("scratch_artifacts_ok")
        return 0

    print("forbidden_root_scratch_artifacts")
    for path in matches:
        print(path)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
