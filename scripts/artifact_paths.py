"""Helpers for keeping temporary artifacts under ignored output paths."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRATCH_ROOT_NAME = "scratch"
OUTPUT_ROOT_NAME = "output"


def _safe_artifact_segment(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("artifact path segment cannot be empty")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip(".-_")
    if not safe:
        raise ValueError("artifact path segment has no safe characters")
    return safe


def scratch_root(project_root: Path | None = None) -> Path:
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    return root / OUTPUT_ROOT_NAME / SCRATCH_ROOT_NAME


def resolve_scratch_artifact_path(
    workflow: str,
    *relative_parts: str | Path,
    project_root: Path | None = None,
) -> Path:
    base = (scratch_root(project_root) / _safe_artifact_segment(workflow)).resolve()
    artifact_path = base.joinpath(*relative_parts).resolve()
    if artifact_path != base and base not in artifact_path.parents:
        raise ValueError(f"scratch artifact path escapes output/scratch: {artifact_path}")
    return artifact_path


def ensure_scratch_artifact_path(
    workflow: str,
    *relative_parts: str | Path,
    project_root: Path | None = None,
) -> Path:
    artifact_path = resolve_scratch_artifact_path(workflow, *relative_parts, project_root=project_root)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    return artifact_path
