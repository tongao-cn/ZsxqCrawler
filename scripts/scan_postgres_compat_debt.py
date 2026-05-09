from __future__ import annotations

import re
from pathlib import Path


PATTERNS = (
    ("INSERT OR REPLACE", re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.IGNORECASE)),
    ("INSERT OR IGNORE", re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE)),
    ("PRAGMA", re.compile(r"\bPRAGMA\s+(?:table_info|journal_mode|foreign_keys)\b", re.IGNORECASE)),
    ("lastrowid", re.compile(r"\blastrowid\b")),
    ("AUTOINCREMENT", re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE)),
)

SEARCH_ROOT = Path("backend")
EXCLUDED_FILES = {
    Path("backend/storage/db_compat.py"),
}


def iter_python_files():
    for path in sorted(SEARCH_ROOT.rglob("*.py")):
        if path in EXCLUDED_FILES:
            continue
        yield path


def scan():
    findings = []
    for path in iter_python_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append((str(path), line_no, label, line.strip()))
    return findings


def main() -> int:
    findings = scan()
    print("# PostgreSQL compatibility debt scan")
    print()
    if not findings:
        print("No SQLite compatibility patterns found.")
        return 0

    current_path = None
    for path, line_no, label, line in findings:
        if path != current_path:
            if current_path is not None:
                print()
            print(f"## {path}")
            current_path = path
        print(f"- {line_no}: {label}: {line}")
    print()
    print(f"Total findings: {len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
