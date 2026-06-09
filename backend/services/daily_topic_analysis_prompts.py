"""Prompt and metadata builders for daily AI reports."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from backend.services.daily_topic_analysis_topics import clip_text


def build_prompt_payload(
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    *,
    max_prompt_chars: int,
) -> str:
    text = build_prompt_payload_unclipped(group_id, report_date, topics)
    return clip_text(text, max_prompt_chars)


def build_prompt_payload_unclipped(group_id: str, report_date: str, topics: List[Dict[str, Any]]) -> str:
    payload = {
        "group_id": group_id,
        "report_date": report_date,
        "topic_count": len(topics),
        "topics": topics,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def split_topics_for_report_chunks(
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    *,
    max_chars: int,
) -> List[List[Dict[str, Any]]]:
    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for topic in topics:
        candidate = [*current, topic]
        candidate_text = build_prompt_payload_unclipped(group_id, report_date, candidate)
        if current and len(candidate_text) > max_chars:
            chunks.append(current)
            current = [topic]
            continue
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def build_empty_report_summary(report_date: str) -> str:
    return (
        "# 每日话题分析报告\n\n"
        f"日期：{report_date}\n\n"
        "当天没有采集到话题。建议先确认当天最新数据已完成抓取，或检查群组是否确实无新增内容。\n"
    )


def collect_report_images(topics: List[Dict[str, Any]], *, max_images_per_report: int) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []
    for topic in topics:
        for image in topic.get("images", []) or []:
            if image.get("url"):
                images.append(image)
                if len(images) >= max_images_per_report:
                    return images

        for comment in topic.get("comments", []) or []:
            for image in comment.get("images", []) or []:
                if image.get("url"):
                    images.append(image)
                    if len(images) >= max_images_per_report:
                        return images
    return images


def build_report_metadata(
    *,
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    report_path: str,
    max_images_per_report: int,
) -> Dict[str, Any]:
    return {
        "group_id": group_id,
        "report_date": report_date,
        "topic_count": len(topics),
        "topic_ids": [topic["topic_id"] for topic in topics],
        "image_refs": [
            image["image_ref"] for image in collect_report_images(topics, max_images_per_report=max_images_per_report)
        ],
        "report_path": report_path,
    }


def build_report_user_prompt(
    prompt_payload: str,
    report_date: str,
    *,
    image_refs: Optional[List[str]] = None,
) -> str:
    image_note = ""
    if image_refs:
        image_note = (
            "\n- 部分话题图片已作为附件随本请求传入；图片顺序与话题数据中的 image_ref 顺序一致。"
            "\n- 如图片内容影响判断，请在相关话题分析中结合文字与图片，不要臆测图片外的信息。"
        )

    return (
        f"请为 {report_date} 的全部话题生成 AI 日报。\n\n"
        "请按以下结构输出：\n"
        "# 每日话题分析报告\n"
        "## 一句话结论\n"
        "## 今日核心洞察\n"
        "## 热点话题 Top 5\n"
        "## 高价值观点与问答\n"
        "## 需要跟进的机会或风险\n"
        "## 明日关注点\n"
        "## 话题索引\n\n"
        "要求：\n"
        "- 每个重点尽量引用 topic_id，方便回溯。\n"
        "- 热点综合阅读、点赞、评论和内容价值判断。\n"
        "- 如果当天话题很少，也要如实说明。"
        f"{image_note}\n"
        "- 不要输出 JSON。\n\n"
        f"话题数据：\n{prompt_payload}"
    )


def build_chunk_summary_user_prompt(
    prompt_payload: str,
    report_date: str,
    *,
    chunk_index: int,
    chunk_count: int,
) -> str:
    return (
        f"请为 {report_date} 的第 {chunk_index}/{chunk_count} 个话题分块生成局部摘要。\n\n"
        "输出中文 Markdown，结构如下：\n"
        "## 分块核心结论\n"
        "## 重要话题与证据\n"
        "## 股票、产业链和概念线索\n"
        "## 风险与待跟进事项\n"
        "## topic_id 索引\n\n"
        "要求：\n"
        "- 只基于本分块输入，不要补充外部信息。\n"
        "- 每个重点尽量引用 topic_id。\n"
        "- 保留能支撑最终日报的高信息密度，不要写寒暄。\n\n"
        f"话题数据：\n{prompt_payload}"
    )


def clip_chunk_summaries_for_final(chunk_summaries: List[str], limit: int) -> Tuple[List[str], bool]:
    clipped = [clip_text(summary, limit) for summary in chunk_summaries]
    return clipped, any(clipped_summary != original for clipped_summary, original in zip(clipped, chunk_summaries))


def build_final_report_user_prompt(chunk_summaries: List[str], report_date: str) -> str:
    joined = "\n\n".join(
        f"<!-- chunk {index + 1} -->\n{summary}" for index, summary in enumerate(chunk_summaries)
    )
    return (
        f"请基于 {report_date} 的多个分块摘要，生成最终 AI 日报。\n\n"
        "请按以下结构输出：\n"
        "# 每日话题分析报告\n"
        "## 一句话结论\n"
        "## 今日核心洞察\n"
        "## 热点话题 Top 5\n"
        "## 高价值观点与问答\n"
        "## 需要跟进的机会或风险\n"
        "## 明日关注点\n"
        "## 话题索引\n\n"
        "要求：\n"
        "- 只能基于分块摘要，不要编造未出现的信息。\n"
        "- 合并重复观点，保留 topic_id 方便回溯。\n"
        "- 不要输出 JSON。\n\n"
        f"分块摘要：\n{joined}"
    )
