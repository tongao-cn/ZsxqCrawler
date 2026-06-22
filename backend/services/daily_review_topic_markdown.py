from __future__ import annotations

import re
from typing import Any

from backend.services.daily_topic_analysis_topics import clip_text


def display_image_url(image: dict[str, Any]) -> str:
    for key in ("local_path", "original_url", "large_url", "thumbnail_url"):
        value = str(image.get(key) or "").strip()
        if value:
            return value.replace("\\", "/")
    return ""


def markdown_cell(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return text.replace("|", "\\|").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def compact_create_time(value: Any) -> str:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return text


def is_truncated_preview(previous: str, current: str) -> bool:
    suffix = "..." if previous.endswith("...") else "…" if previous.endswith("…") else ""
    if not suffix:
        return False
    prefix = previous[: -len(suffix)].strip()
    return len(prefix) >= 6 and current.startswith(prefix)


def drop_leading_preview_block(lines: list[str]) -> list[str]:
    first_index = None
    first_compact = ""
    for index, line in enumerate(lines):
        compact = re.sub(r"\s+", " ", line.strip())
        if compact:
            first_index = index
            first_compact = compact
            break
    if first_index is None:
        return lines

    window_end = min(len(lines), first_index + 8)
    for index in range(first_index + 1, window_end):
        compact = re.sub(r"\s+", " ", lines[index].strip())
        if compact != first_compact:
            continue
        preview_lines = [re.sub(r"\s+", " ", line.strip()) for line in lines[first_index + 1 : index]]
        if any(line.endswith("...") or line.endswith("…") for line in preview_lines):
            return lines[index:]
    return lines


def clean_markdown_content(content: str) -> str:
    lines: list[str] = []
    previous_non_empty_index: int | None = None
    previous_compact = ""
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        compact = re.sub(r"\s+", " ", line.strip())
        if compact and previous_non_empty_index is not None:
            if compact == previous_compact:
                continue
            if is_truncated_preview(previous_compact, compact):
                del lines[previous_non_empty_index:]
                previous_non_empty_index = None
        lines.append(line)
        if compact:
            previous_non_empty_index = len(lines) - 1
            previous_compact = compact
    return "\n".join(drop_leading_preview_block(lines)).strip()


def topic_display_title(topic: dict[str, Any]) -> str:
    content_first_line = first_non_empty_line(clean_markdown_content(str(topic.get("content") or "")))
    for value in (content_first_line, topic.get("first_line"), topic.get("title"), topic.get("topic_id")):
        title = re.sub(r"\s+", " ", str(value or "").strip())
        if title:
            return clip_text(title, 80).replace("\n", " ")
    return "未命名话题"


def first_non_empty_line(text: str) -> str:
    for raw_line in re.split(r"[\r\n]+", text):
        line = re.sub(r"\s+", " ", raw_line.strip())
        if line:
            return line
    return ""


def count_table_lines(title: str, counts: dict[str, int]) -> list[str]:
    lines = [f"### {title}", "", "| 名称 | 数量 |", "| --- | ---: |"]
    if not counts:
        lines.append("| - | 0 |")
        return lines
    for name, count in counts.items():
        lines.append(f"| {markdown_cell(name)} | {count} |")
    return lines


def topic_markdown(topic: dict[str, Any], index: int) -> str:
    header = f"### {index}. {topic_display_title(topic)}"
    metrics = topic.get("metrics") or {}
    source = f"{topic.get('group_name', '')} / {topic.get('matched_rule', '')}"
    meta_lines = [
        "| 字段 | 内容 |",
        "| --- | --- |",
        f"| 时间 | {markdown_cell(compact_create_time(topic.get('create_time')))} |",
        f"| 来源 | {markdown_cell(source)} |",
        f"| 作者 | {markdown_cell(topic.get('author'))} |",
        f"| 话题ID | {markdown_cell(topic.get('topic_id'))} |",
        (
            f"| 指标 | 赞 {metrics.get('likes_count', 0)} / 评论 {metrics.get('comments_count', 0)} / "
            f"阅读 {metrics.get('reading_count', 0)} |"
        ),
    ]
    content = clean_markdown_content(str(topic.get("content") or ""))
    image_lines: list[str] = []
    for index, image in enumerate(topic.get("images") or [], start=1):
        image_url = display_image_url(image)
        if image_url:
            image_lines.append(f"![{topic.get('topic_id', '')} image {index}]({image_url})")
    images = "\n\n".join(image_lines)
    body_parts = []
    if content:
        body_parts.extend(["#### 正文", content])
    if images:
        body_parts.extend(["#### 图片", images])
    body = "\n\n".join(body_parts)
    meta = "\n".join(meta_lines)
    return f"{header}\n\n{meta}\n\n{body}\n"


def render_review_topics_markdown(payload: dict[str, Any]) -> str:
    topics = payload.get("topics") or []
    group_ids = payload.get("group_ids") or []
    lines = [
        f"# {payload['report_date']} {payload['slot_label']}话题",
        "",
        f"> {payload['slot_label']} | 命中 {payload['matched_count']} 条 | 状态 {payload['level']}",
        "",
        "## 概览",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 报告日期 | {markdown_cell(payload.get('report_date'))} |",
        f"| 类型 | {markdown_cell(payload.get('slot_label'))} |",
        f"| 命中数量 | {payload.get('matched_count', 0)} 条 |",
        f"| 群组 | {markdown_cell(', '.join(group_ids))} |",
    ]
    if payload.get("started_at"):
        lines.append(f"| 开始时间 | {markdown_cell(payload.get('started_at'))} |")
    if payload.get("finished_at"):
        lines.append(f"| 完成时间 | {markdown_cell(payload.get('finished_at'))} |")

    lines.extend(["", "## 命中分布", ""])
    lines.extend(count_table_lines("按类型", payload.get("matched_rules") or {}))
    lines.append("")
    lines.extend(count_table_lines("按群组", payload.get("matched_groups") or {}))
    lines.append("")

    if not topics:
        lines.append("## 详细内容")
        lines.append("")
        lines.append("未匹配到早报/晚报话题。")
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(["## 话题目录", "", "| # | 时间 | 群组 | 类型 | 标题 |", "| ---: | --- | --- | --- | --- |"])
    for index, topic in enumerate(topics, start=1):
        lines.append(
            "| "
            f"{index} | "
            f"{markdown_cell(compact_create_time(topic.get('create_time')))} | "
            f"{markdown_cell(topic.get('group_name'))} | "
            f"{markdown_cell(topic.get('matched_rule'))} | "
            f"{markdown_cell(topic_display_title(topic))} |"
        )

    lines.extend(["", "## 详细内容", ""])
    for index, topic in enumerate(topics, start=1):
        lines.append(topic_markdown(topic, index))
    return "\n".join(lines).rstrip() + "\n"
