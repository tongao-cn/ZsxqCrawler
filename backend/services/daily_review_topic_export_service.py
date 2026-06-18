from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Pattern

from backend.services.daily_topic_analysis_topics import clip_text
from backend.storage.db_compat import connect


ReviewTopicSlot = Literal["morning", "evening"]

SHANGHAI_TZ = timezone(timedelta(hours=8))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output" / "exports" / "daily-review-topics"
DEFAULT_GROUP_IDS = ("51111112855254", "15552822451452", "28888222124181")


@dataclass(frozen=True)
class ReviewTopicRule:
    name: str
    pattern: Pattern[str]


MORNING_RULES = (
    ReviewTopicRule("盘前热点事件", re.compile(r"盘前热点事件", re.I)),
    ReviewTopicRule("盘前热点", re.compile(r"\d{1,2}月\d{1,2}日，?盘前热点", re.I)),
    ReviewTopicRule("股市早报", re.compile(r"\d{1,2}月\d{1,2}日股市早报|股市早报", re.I)),
    ReviewTopicRule("TMT早报", re.compile(r"^TMTB?\s*.*(早|晨|盘前|收盘综述|市场动态|要闻|速览|摘要|突破)", re.I)),
    ReviewTopicRule("盘前PH解盘追踪", re.compile(r"盘前\d{3,4}.*PH解盘追踪|PH解盘追踪", re.I)),
    ReviewTopicRule(
        "高盛中国开盘",
        re.compile(r"GS\s*CHINA\s*OPEN|高盛中国开盘|交易台\s*[–-]\s*高盛中国开盘", re.I),
    ),
)

EVENING_RULES = (
    ReviewTopicRule("复盘笔记", re.compile(r"\d{1,2}月\d{1,2}\s*日?复盘笔记|复盘笔记", re.I)),
    ReviewTopicRule("复盘数据/市场情绪", re.compile(r"复盘数据/市场情绪", re.I)),
    ReviewTopicRule("盘后解读", re.compile(r"盘后解读", re.I)),
    ReviewTopicRule("盘后热门题材", re.compile(r"盘后热门题材", re.I)),
    ReviewTopicRule("东财策略每日复盘", re.compile(r"东财策略.*每日复盘|每日复盘.*东财策略", re.I)),
    ReviewTopicRule("日报", re.compile(r"^日报\d{4}[:：]", re.I)),
    ReviewTopicRule(
        "行业/价格日报",
        re.compile(r"价格日报|行业日报|市场日报|机器人行业日报|商业航天日报|AI\s*日报|AI日报|TMT.*日报", re.I),
    ),
    ReviewTopicRule("晚报", re.compile(r"行业新闻晚报|晚报", re.I)),
    ReviewTopicRule("市场总结/回顾", re.compile(r"市场总结|市场回顾", re.I)),
)

SLOT_RULES: dict[ReviewTopicSlot, tuple[ReviewTopicRule, ...]] = {
    "morning": MORNING_RULES,
    "evening": EVENING_RULES,
}

SLOT_LABELS: dict[ReviewTopicSlot, str] = {
    "morning": "早报",
    "evening": "晚报",
}


def normalize_review_slot(value: str) -> ReviewTopicSlot:
    text = str(value or "").strip().lower()
    aliases = {
        "morning": "morning",
        "am": "morning",
        "pre": "morning",
        "pre_market": "morning",
        "zaobao": "morning",
        "早报": "morning",
        "盘前": "morning",
        "evening": "evening",
        "pm": "evening",
        "post": "evening",
        "post_market": "evening",
        "wanbao": "evening",
        "晚报": "evening",
        "盘后": "evening",
    }
    try:
        return aliases[text]  # type: ignore[return-value]
    except KeyError as exc:
        raise ValueError(f"unsupported review topic slot: {value}") from exc


def shanghai_today() -> date:
    return datetime.now(SHANGHAI_TZ).date()


def parse_report_date(value: str | None) -> date:
    if not value:
        return shanghai_today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _format_bj(dt: datetime) -> str:
    return dt.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800"


def review_topic_time_bounds(report_date: date, slot: ReviewTopicSlot) -> tuple[str, str]:
    if slot == "morning":
        start_dt = datetime.combine(report_date - timedelta(days=1), datetime.min.time(), tzinfo=SHANGHAI_TZ)
        start_dt = start_dt.replace(hour=18)
        end_dt = datetime.combine(report_date, datetime.min.time(), tzinfo=SHANGHAI_TZ).replace(hour=11, minute=30)
        return _format_bj(start_dt), _format_bj(end_dt)
    start_dt = datetime.combine(report_date, datetime.min.time(), tzinfo=SHANGHAI_TZ).replace(hour=12)
    end_dt = datetime.combine(report_date + timedelta(days=1), datetime.min.time(), tzinfo=SHANGHAI_TZ).replace(hour=1, minute=30)
    return _format_bj(start_dt), _format_bj(end_dt)


def normalize_group_ids(values: Iterable[str] | None) -> list[str]:
    raw_values = list(values or DEFAULT_GROUP_IDS)
    group_ids: list[str] = []
    for raw in raw_values:
        for part in str(raw).replace("，", ",").split(","):
            group_id = part.strip()
            if group_id and group_id not in group_ids:
                group_ids.append(group_id)
    if not group_ids:
        raise ValueError("at least one group id is required")
    return group_ids


def _group_id_param(group_id: str) -> Any:
    return int(group_id) if group_id.isdigit() else group_id


def first_non_empty_line(text: str) -> str:
    for raw_line in re.split(r"[\r\n]+", text):
        line = re.sub(r"\s+", " ", raw_line.strip())
        if line:
            return line
    return ""


def topic_content(row: Any) -> str:
    parts = [
        row["title"],
        row["talk_text"],
        row["question_text"],
        row["answer_text"],
        row["detail_text"],
    ]
    return "\n".join(str(part or "").strip() for part in parts if str(part or "").strip())


def _display_image_url(image: dict[str, Any]) -> str:
    for key in ("local_path", "original_url", "large_url", "thumbnail_url"):
        value = str(image.get(key) or "").strip()
        if value:
            return value.replace("\\", "/")
    return ""


def _image_row_to_payload(row: Any) -> dict[str, Any]:
    return {
        "image_id": str(row["image_id"] or ""),
        "type": row["type"] or "",
        "thumbnail_url": row["thumbnail_url"] or "",
        "thumbnail_width": row["thumbnail_width"] or 0,
        "thumbnail_height": row["thumbnail_height"] or 0,
        "large_url": row["large_url"] or "",
        "large_width": row["large_width"] or 0,
        "large_height": row["large_height"] or 0,
        "original_url": row["original_url"] or "",
        "original_width": row["original_width"] or 0,
        "original_height": row["original_height"] or 0,
        "local_path": row["local_path"] or "",
    }


def _load_images_by_topic(conn: Any, topic_ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    normalized_topic_ids = [str(topic_id).strip() for topic_id in topic_ids if str(topic_id).strip()]
    if not normalized_topic_ids:
        return {}
    placeholders = ",".join("?" for _ in normalized_topic_ids)
    rows = conn.execute(
        f"""
        SELECT
            topic_id, image_id, type, thumbnail_url, thumbnail_width, thumbnail_height,
            large_url, large_width, large_height, original_url, original_width,
            original_height, local_path
        FROM images
        WHERE topic_id IN ({placeholders})
        ORDER BY topic_id ASC, image_id ASC
        """,
        [int(topic_id) if topic_id.isdigit() else topic_id for topic_id in normalized_topic_ids],
    ).fetchall()
    images_by_topic: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        images_by_topic.setdefault(str(row["topic_id"] or ""), []).append(_image_row_to_payload(row))
    return images_by_topic


def match_review_rule(slot: ReviewTopicSlot, text: str) -> ReviewTopicRule | None:
    first_line = first_non_empty_line(text)
    if not first_line:
        return None
    for rule in SLOT_RULES[slot]:
        if rule.pattern.search(first_line):
            return rule
    return None


def _topic_row_to_payload(
    row: Any,
    slot: ReviewTopicSlot,
    rule: ReviewTopicRule,
    *,
    max_topic_chars: int,
    images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    content = topic_content(row)
    first_line = first_non_empty_line(content)
    return {
        "slot": slot,
        "slot_label": SLOT_LABELS[slot],
        "matched_rule": rule.name,
        "group_id": str(row["group_id"] or ""),
        "group_name": row["group_name"] or "",
        "topic_id": str(row["topic_id"] or ""),
        "type": row["type"] or "",
        "title": row["title"] or "",
        "author": row["author"] or "",
        "create_time": row["create_time"] or "",
        "metrics": {
            "likes_count": row["likes_count"] or 0,
            "comments_count": row["comments_count"] or 0,
            "reading_count": row["reading_count"] or 0,
            "readers_count": row["readers_count"] or 0,
        },
        "first_line": first_line,
        "content": clip_text(content, max_topic_chars),
        "images": images or [],
    }


def fetch_review_topics(
    conn: Any,
    *,
    group_ids: Iterable[str],
    report_date: date,
    slot: ReviewTopicSlot,
    max_topic_chars: int = 8000,
) -> list[dict[str, Any]]:
    normalized_group_ids = normalize_group_ids(group_ids)
    start_time, end_time = review_topic_time_bounds(report_date, slot)
    placeholders = ",".join("?" for _ in normalized_group_ids)
    rows = conn.execute(
        f"""
        SELECT
            t.group_id, g.name AS group_name, t.topic_id, t.type, t.title, t.create_time,
            t.likes_count, t.comments_count, t.reading_count, t.readers_count,
            COALESCE(talk_owner.name, q_owner.name, a_owner.name, '') AS author,
            COALESCE(talk.text, '') AS talk_text,
            COALESCE(q.text, '') AS question_text,
            COALESCE(a.text, '') AS answer_text,
            COALESCE(td.full_text, '') AS detail_text
        FROM topics t
        LEFT JOIN groups g ON g.group_id = t.group_id
        LEFT JOIN talks talk ON talk.topic_id = t.topic_id
        LEFT JOIN users talk_owner ON talk.owner_user_id = talk_owner.user_id
        LEFT JOIN questions q ON q.topic_id = t.topic_id
        LEFT JOIN users q_owner ON q.owner_user_id = q_owner.user_id
        LEFT JOIN answers a ON a.topic_id = t.topic_id
        LEFT JOIN users a_owner ON a.owner_user_id = a_owner.user_id
        LEFT JOIN topic_details td ON td.topic_id = t.topic_id
        WHERE t.group_id IN ({placeholders})
          AND t.create_time >= ?
          AND t.create_time < ?
        ORDER BY t.create_time ASC, t.topic_id ASC
        """,
        [*(_group_id_param(group_id) for group_id in normalized_group_ids), start_time, end_time],
    ).fetchall()

    matched_rows: list[tuple[Any, ReviewTopicRule]] = []
    for row in rows:
        content = topic_content(row)
        rule = match_review_rule(slot, content)
        if rule:
            matched_rows.append((row, rule))
    images_by_topic = _load_images_by_topic(conn, [str(row["topic_id"] or "") for row, _rule in matched_rows])
    topics: list[dict[str, Any]] = []
    for row, rule in matched_rows:
        topic_id = str(row["topic_id"] or "")
        topics.append(
            _topic_row_to_payload(
                row,
                slot,
                rule,
                max_topic_chars=max_topic_chars,
                images=images_by_topic.get(topic_id, []),
            )
        )
    return topics


def load_review_topics(
    *,
    group_ids: Iterable[str],
    report_date: date,
    slot: ReviewTopicSlot,
    max_topic_chars: int = 8000,
) -> list[dict[str, Any]]:
    conn = connect()
    try:
        return fetch_review_topics(
            conn,
            group_ids=group_ids,
            report_date=report_date,
            slot=slot,
            max_topic_chars=max_topic_chars,
        )
    finally:
        conn.close()


def _counts_by(topics: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for topic in topics:
        key = str(topic.get(field) or "")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_review_topic_export(
    *,
    group_ids: Iterable[str],
    report_date: date,
    slot: ReviewTopicSlot,
    topics: list[dict[str, Any]],
    crawl_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_group_ids = normalize_group_ids(group_ids)
    return {
        "level": "OK" if topics else "WARN",
        "group_ids": normalized_group_ids,
        "report_date": report_date.isoformat(),
        "slot": slot,
        "slot_label": SLOT_LABELS[slot],
        "matched_count": len(topics),
        "matched_rules": _counts_by(topics, "matched_rule"),
        "matched_groups": _counts_by(topics, "group_name"),
        "crawl_results": crawl_results or [],
        "topics": topics,
    }


def _topic_markdown(topic: dict[str, Any]) -> str:
    header = (
        f"### {topic.get('create_time', '')} "
        f"{topic.get('group_name', '')} / {topic.get('matched_rule', '')} / {topic.get('topic_id', '')}"
    ).strip()
    metrics = topic.get("metrics") or {}
    meta = (
        f"- author: {topic.get('author', '')}\n"
        f"- metrics: likes={metrics.get('likes_count', 0)}, comments={metrics.get('comments_count', 0)}, "
        f"reads={metrics.get('reading_count', 0)}"
    )
    content = str(topic.get("content") or "").strip()
    image_lines: list[str] = []
    for index, image in enumerate(topic.get("images") or [], start=1):
        image_url = _display_image_url(image)
        if image_url:
            image_lines.append(f"![{topic.get('topic_id', '')} image {index}]({image_url})")
    images = "\n\n".join(image_lines)
    body_parts = [part for part in (content, images) if part]
    body = "\n\n".join(body_parts)
    return f"{header}\n\n{meta}\n\n{body}\n"


def render_review_topics_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['slot_label']}话题导出 {payload['report_date']}",
        "",
        f"- level: {payload['level']}",
        f"- matched_count: {payload['matched_count']}",
        f"- group_ids: {', '.join(payload['group_ids'])}",
        "",
    ]
    topics = payload.get("topics") or []
    if not topics:
        lines.append("未匹配到早报/晚报话题。")
        return "\n".join(lines).rstrip() + "\n"
    for topic in topics:
        lines.append(_topic_markdown(topic))
    return "\n".join(lines).rstrip() + "\n"


def write_review_topic_export(payload: dict[str, Any], output_dir: Path | str | None = None) -> dict[str, str]:
    if output_dir is None:
        output_path = DEFAULT_OUTPUT_ROOT / payload["report_date"] / payload["slot"]
    else:
        output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    topics_path = output_path / "topics.json"
    summary_path = output_path / "summary.json"
    markdown_path = output_path / "topics.md"

    topics_path.write_text(json.dumps(payload["topics"], ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    summary = {key: value for key, value in payload.items() if key != "topics"}
    summary["output_files"] = {
        "topics_json": str(topics_path),
        "summary_json": str(summary_path),
        "markdown": str(markdown_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    markdown_path.write_text(render_review_topics_markdown(payload), encoding="utf-8")

    return {
        "topics_json": str(topics_path),
        "summary_json": str(summary_path),
        "markdown": str(markdown_path),
    }


__all__ = [
    "DEFAULT_GROUP_IDS",
    "DEFAULT_OUTPUT_ROOT",
    "EVENING_RULES",
    "MORNING_RULES",
    "ReviewTopicRule",
    "ReviewTopicSlot",
    "build_review_topic_export",
    "fetch_review_topics",
    "load_review_topics",
    "match_review_rule",
    "normalize_group_ids",
    "normalize_review_slot",
    "parse_report_date",
    "render_review_topics_markdown",
    "review_topic_time_bounds",
    "write_review_topic_export",
]
