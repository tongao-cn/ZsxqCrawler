from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

from backend.crawlers.zsxq_file_downloader import ZSXQFileDownloader


INITIAL_UA_RE = re.compile(r"UA分类:\s*(?P<label>.+?)\s*$")
RETRY_UA_RE = re.compile(r"重试#\d+:\s*使用新的User-Agent:\s*(?P<ua>.+)$")
FAIL_1059_RE = re.compile(r"代码:\s*1059")
SUCCESS_RE = re.compile(r"下载完成:")


def _ua_label(user_agent: str) -> str:
    return ZSXQFileDownloader._user_agent_label(user_agent)


def analyze(path: Path) -> dict[str, Counter[str]]:
    initial_attempts: Counter[str] = Counter()
    initial_1059: Counter[str] = Counter()
    retry_attempts: Counter[str] = Counter()
    retry_success_after_1059: Counter[str] = Counter()

    current_initial_ua: str | None = None
    pending_1059 = False
    current_retry_ua: str | None = None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        initial_match = INITIAL_UA_RE.search(line)
        if initial_match:
            current_initial_ua = initial_match.group("label").strip()
            initial_attempts[current_initial_ua] += 1
            pending_1059 = False
            current_retry_ua = None
            continue

        if FAIL_1059_RE.search(line):
            if current_initial_ua:
                initial_1059[current_initial_ua] += 1
            pending_1059 = True
            continue

        retry_match = RETRY_UA_RE.search(line)
        if retry_match:
            current_retry_ua = _ua_label(retry_match.group("ua"))
            retry_attempts[current_retry_ua] += 1
            continue

        if SUCCESS_RE.search(line) and pending_1059 and current_retry_ua:
            retry_success_after_1059[current_retry_ua] += 1
            pending_1059 = False
            current_retry_ua = None

    return {
        "initial_attempts": initial_attempts,
        "initial_1059": initial_1059,
        "retry_attempts": retry_attempts,
        "retry_success_after_1059": retry_success_after_1059,
    }


def analyze_csv(path: Path) -> dict[str, Counter[str]]:
    initial_attempts: Counter[str] = Counter()
    initial_success: Counter[str] = Counter()
    initial_1059: Counter[str] = Counter()
    retry_success: Counter[str] = Counter()
    header_attempts: Counter[str] = Counter()
    header_1059: Counter[str] = Counter()

    with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        for row in csv.DictReader(file_obj):
            ua_label = row.get("ua_label") or "unknown"
            header_profile = row.get("header_profile") or "unknown"
            phase = row.get("phase") or ""
            status = row.get("status") or ""
            api_code = str(row.get("api_code") or "")
            if phase == "download_url_request":
                initial_attempts[ua_label] += 1
                header_attempts[header_profile] += 1
            elif phase == "download_url_response" and status == "api_success":
                initial_success[ua_label] += 1
            elif phase == "download_url_response" and api_code == "1059":
                initial_1059[ua_label] += 1
                header_1059[header_profile] += 1
            elif phase == "download_url_retry_response" and status == "api_success":
                retry_success[ua_label] += 1
    return {
        "initial_attempts": initial_attempts,
        "initial_success": initial_success,
        "initial_1059": initial_1059,
        "retry_success": retry_success,
        "header_attempts": header_attempts,
        "header_1059": header_1059,
    }


def _print_counter(title: str, counter: Counter[str]) -> None:
    print(title)
    if not counter:
        print("  [none]")
        return
    for key, count in counter.most_common():
        print(f"  {key}\t{count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze UA labels in analysis-ready download logs.")
    parser.add_argument("log_path", type=Path)
    args = parser.parse_args()
    if args.log_path.suffix.lower() == ".csv":
        stats = analyze_csv(args.log_path)
    else:
        stats = analyze(args.log_path)
    for title, counter in stats.items():
        _print_counter(title, counter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
