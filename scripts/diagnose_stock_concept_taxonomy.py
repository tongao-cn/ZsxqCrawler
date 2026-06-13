from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.db_compat import connect  # noqa: E402


TAXONOMY_PATH = PROJECT_ROOT / "frontend" / "src" / "components" / "DailyTopicAnalysisPanelUtils.ts"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose daily stock concept taxonomy coverage.")
    parser.add_argument("--group-id", default="", help="Group id. Defaults to the latest completed group.")
    parser.add_argument("--as-of", default="", help="Latest completed report date to use, YYYY-MM-DD.")
    parser.add_argument("--days", type=int, default=11, help="Trailing days for the recent scope.")
    parser.add_argument("--top", type=int, default=30, help="Rows to show for top tables.")
    parser.add_argument("--csv", default="", help="Optional CSV path for top unmapped recent terms.")
    return parser.parse_args()


def _literal_list(source: str) -> list[str]:
    value = ast.literal_eval(source)
    return [str(item) for item in value if str(item).strip()]


def load_taxonomy() -> tuple[dict[str, str], dict[str, str]]:
    content = TAXONOMY_PATH.read_text(encoding="utf-8")
    concept_block = content.split("const CONCEPT_ALIAS_GROUPS", 1)[1].split("const CONCEPT_ALIAS_MAP", 1)[0]
    signal_block = content.split("const SIGNAL_TAG_ALIAS_GROUPS", 1)[1].split("const SIGNAL_TAG_ALIAS_MAP", 1)[0]

    concept_map: dict[str, str] = {}
    for concept, aliases_source in re.findall(r"concept: '([^']+)',\s*aliases: (\[[^\]]*\])", concept_block, re.S):
        concept_map[concept.lower()] = concept
        for alias in _literal_list(aliases_source):
            concept_map[alias.lower()] = concept

    signal_map: dict[str, str] = {}
    for tag, aliases_source in re.findall(r"tag: '([^']+)',\s*aliases: (\[[^\]]*\])", signal_block, re.S):
        signal_map[tag.lower()] = tag
        for alias in _literal_list(aliases_source):
            signal_map[alias.lower()] = tag

    return concept_map, signal_map


def parse_json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def classify_term(term: str, concept_map: dict[str, str], signal_map: dict[str, str]) -> tuple[str, str]:
    key = term.lower()
    if key in signal_map:
        return "signal", signal_map[key]
    if key in concept_map:
        return "concept", concept_map[key]
    return "unmapped", term


def latest_completed_group_date(group_id: str, as_of: str) -> tuple[str, str]:
    conditions = ["status = 'completed'", "concepts_json IS NOT NULL", "concepts_json <> ''", "concepts_json <> '[]'"]
    params: list[Any] = []
    if group_id:
        conditions.append("group_id = ?")
        params.append(group_id)
    if as_of:
        conditions.append("report_date::date <= ?::date")
        params.append(as_of)

    conn = connect(row_factory=True)
    try:
        row = conn.execute(
            f"""
            SELECT group_id, report_date, COUNT(*) AS rows
            FROM daily_stock_concepts
            WHERE {" AND ".join(conditions)}
            GROUP BY group_id, report_date
            ORDER BY report_date DESC, rows DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise RuntimeError("No completed daily_stock_concepts rows with concepts were found.")
    return str(row["group_id"]), str(row["report_date"])


def load_scope_rows(group_id: str, as_of: str, days: int, scope: str) -> list[Any]:
    if scope == "latest":
        where = "group_id = ? AND report_date::date = ?::date"
        params: list[Any] = [group_id, as_of]
    elif scope == "recent":
        where = "group_id = ? AND report_date::date <= ?::date AND report_date::date >= (?::date - (? * INTERVAL '1 day'))::date"
        params = [group_id, as_of, as_of, max(days - 1, 0)]
    else:
        raise ValueError(f"Unsupported scope: {scope}")

    conn = connect(row_factory=True)
    try:
        return conn.execute(
            f"""
            SELECT report_date, stock_name, concepts_json, topic_ids_json
            FROM daily_stock_concepts
            WHERE {where}
            ORDER BY report_date DESC, stock_name ASC
            """,
            params,
        ).fetchall()
    finally:
        conn.close()


def summarize(rows: Iterable[Any], concept_map: dict[str, str], signal_map: dict[str, str]) -> dict[str, Any]:
    raw_counter: Counter[str] = Counter()
    normalized_counter: Counter[str] = Counter()
    class_counter: Counter[str] = Counter()
    topics_by_raw: dict[str, set[str]] = defaultdict(set)
    stocks_by_raw: dict[str, set[str]] = defaultdict(set)
    dates_by_raw: dict[str, set[str]] = defaultdict(set)
    topics_by_normalized: dict[str, set[str]] = defaultdict(set)
    stocks_by_normalized: dict[str, set[str]] = defaultdict(set)

    row_count = 0
    rows_with_concepts = 0
    for row in rows:
        row_count += 1
        report_date = str(row["report_date"] or "")
        stock_name = str(row["stock_name"] or "")
        concepts = parse_json_list(row["concepts_json"])
        if concepts:
            rows_with_concepts += 1
        topic_ids = parse_json_list(row["topic_ids_json"])
        topic_set = set(topic_ids) or {f"{report_date}:{stock_name}"}
        for term in concepts:
            class_name, normalized = classify_term(term, concept_map, signal_map)
            raw_counter[term] += 1
            normalized_counter[normalized] += 1
            class_counter[class_name] += 1
            topics_by_raw[term].update(topic_set)
            stocks_by_raw[term].add(stock_name)
            dates_by_raw[term].add(report_date)
            topics_by_normalized[normalized].update(topic_set)
            stocks_by_normalized[normalized].add(stock_name)

    raw_hits = sum(raw_counter.values())
    mapped_hits = class_counter["concept"] + class_counter["signal"]
    normalized_unique = len(normalized_counter)
    raw_unique = len(raw_counter)

    top_unmapped = [
        {
            "term": term,
            "topic_count": len(topics_by_raw[term]),
            "stock_count": len(stocks_by_raw[term]),
            "date_count": len(dates_by_raw[term]),
            "hit_count": raw_counter[term],
        }
        for term, _ in sorted(
            ((term, count) for term, count in raw_counter.items() if classify_term(term, concept_map, signal_map)[0] == "unmapped"),
            key=lambda item: (-len(topics_by_raw[item[0]]), -len(stocks_by_raw[item[0]]), item[0]),
        )
    ]

    top_normalized = [
        {
            "name": term,
            "topic_count": len(topics_by_normalized[term]),
            "stock_count": len(stocks_by_normalized[term]),
            "hit_count": normalized_counter[term],
        }
        for term, _ in sorted(
            normalized_counter.items(),
            key=lambda item: (-len(topics_by_normalized[item[0]]), -len(stocks_by_normalized[item[0]]), item[0]),
        )
    ]

    return {
        "rows": row_count,
        "rows_with_concepts": rows_with_concepts,
        "raw_hits": raw_hits,
        "raw_unique": raw_unique,
        "normalized_unique": normalized_unique,
        "concept_hits": class_counter["concept"],
        "signal_hits": class_counter["signal"],
        "unmapped_hits": class_counter["unmapped"],
        "mapped_hits": mapped_hits,
        "mapped_rate": (mapped_hits / raw_hits * 100) if raw_hits else 0.0,
        "unique_reduction": ((1 - normalized_unique / raw_unique) * 100) if raw_unique else 0.0,
        "top_unmapped": top_unmapped,
        "top_normalized": top_normalized,
    }


def print_summary(scope: str, summary: dict[str, Any], top: int) -> None:
    print(f"## {scope}")
    print(
        "\t".join(
            [
                f"rows={summary['rows']}",
                f"rows_with_concepts={summary['rows_with_concepts']}",
                f"raw_hits={summary['raw_hits']}",
                f"raw_unique={summary['raw_unique']}",
                f"normalized_unique={summary['normalized_unique']}",
                f"concept_hits={summary['concept_hits']}",
                f"signal_hits={summary['signal_hits']}",
                f"unmapped_hits={summary['unmapped_hits']}",
                f"mapped_rate={summary['mapped_rate']:.1f}%",
                f"unique_reduction={summary['unique_reduction']:.1f}%",
            ]
        )
    )
    print("top_unmapped\tterm\ttopics\tstocks\tdates\thits")
    for index, item in enumerate(summary["top_unmapped"][:top], start=1):
        print(
            f"{index}\t{item['term']}\t{item['topic_count']}\t{item['stock_count']}\t{item['date_count']}\t{item['hit_count']}"
        )
    print("top_normalized\tname\ttopics\tstocks\thits")
    for index, item in enumerate(summary["top_normalized"][:top], start=1):
        print(f"{index}\t{item['name']}\t{item['topic_count']}\t{item['stock_count']}\t{item['hit_count']}")


def write_unmapped_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["term", "topic_count", "stock_count", "date_count", "hit_count"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    concept_map, signal_map = load_taxonomy()
    group_id, as_of = latest_completed_group_date(args.group_id.strip(), args.as_of.strip())
    print(
        f"taxonomy\tconcept_aliases={len(concept_map)}\tsignal_aliases={len(signal_map)}\tgroup_id={group_id}\tas_of={as_of}"
    )

    latest_summary = summarize(load_scope_rows(group_id, as_of, args.days, "latest"), concept_map, signal_map)
    recent_summary = summarize(load_scope_rows(group_id, as_of, args.days, "recent"), concept_map, signal_map)
    print_summary("latest_complete", latest_summary, args.top)
    print_summary(f"recent_{args.days}d", recent_summary, args.top)

    if args.csv:
      write_unmapped_csv(Path(args.csv), recent_summary["top_unmapped"])
      print(f"csv_written\t{args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
