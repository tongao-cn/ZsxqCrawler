"""Daily AI reports for group topics."""

from __future__ import annotations

import base64
import json
import mimetypes
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from openai import OpenAI

from backend.core.ai_provider_config import (
    get_default_base_url,
    get_default_model,
    get_default_wire_api,
    get_openai_compatible_config,
    get_summary_reasoning_effort,
)
from backend.core.db_path_manager import get_db_path_manager
from backend.core.image_cache_manager import get_image_cache_manager
from backend.storage.db_compat import connect


MAX_TOPIC_CHARS = 5000
MAX_PROMPT_CHARS = 60000
MAX_IMAGES_PER_REPORT = 12
MAX_IMAGES_PER_TOPIC = 2
MAX_IMAGE_BYTES = 4 * 1024 * 1024
DEFAULT_COMMENTS_PER_TOPIC = 8
PROMPT_VERSION = "daily-topic-report-v1"
BJ_TZ = timezone(timedelta(hours=8))


def _log(log_callback: Optional[Callable[[str], None]], message: str) -> None:
    if log_callback:
        log_callback(message)


def _parse_report_date(value: Optional[str]) -> date:
    if not value:
        return datetime.now(BJ_TZ).date()
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError("date 必须是 YYYY-MM-DD 格式") from exc


def _date_bounds(report_date: date) -> Tuple[str, str]:
    start_dt = datetime.combine(report_date, time.min, tzinfo=BJ_TZ)
    end_dt = start_dt + timedelta(days=1)
    return (
        start_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800",
        end_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0800",
    )


def _clip(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...[内容过长，已截断]"


def _image_row_to_payload(row: Any, image_ref: str) -> Dict[str, Any]:
    url = row["large_url"] or row["original_url"] or row["thumbnail_url"] or ""
    return {
        "image_ref": image_ref,
        "image_id": row["image_id"],
        "url": url,
        "width": row["large_width"] or row["original_width"] or row["thumbnail_width"] or 0,
        "height": row["large_height"] or row["original_height"] or row["thumbnail_height"] or 0,
        "size": row["original_size"] or 0,
    }


def _connect_topics_db(group_id: str):
    return connect(row_factory=True)


def _ensure_report_table(conn: Any) -> None:
    """Schema is managed by manage-postgres-core-schema; runtime DDL is disabled."""
    return None


def _upsert_report(
    conn: Any,
    *,
    group_id: str,
    report_date: str,
    topic_count: int,
    model: str,
    summary_markdown: str,
    raw_json: Dict[str, Any],
    status: str,
    error: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO daily_ai_reports (
            group_id, report_date, topic_count, model, prompt_version,
            summary_markdown, raw_json, status, error, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(group_id, report_date) DO UPDATE SET
            topic_count = excluded.topic_count,
            model = excluded.model,
            prompt_version = excluded.prompt_version,
            summary_markdown = excluded.summary_markdown,
            raw_json = excluded.raw_json,
            status = excluded.status,
            error = excluded.error,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            group_id,
            report_date,
            topic_count,
            model,
            PROMPT_VERSION,
            summary_markdown,
            json.dumps(raw_json, ensure_ascii=False),
            status,
            error,
        ),
    )
    conn.commit()


def _fetch_topics_for_date(
    conn: Any,
    *,
    group_id: str,
    report_date: date,
    comments_per_topic: int,
) -> List[Dict[str, Any]]:
    start_time, end_time = _date_bounds(report_date)
    rows = conn.execute(
        """
        SELECT
            t.topic_id, t.group_id, t.type, t.title, t.create_time,
            t.likes_count, t.comments_count, t.reading_count, t.readers_count,
            t.digested, t.sticky,
            talk.text AS talk_text,
            talk_owner.name AS talk_owner_name,
            q.text AS question_text,
            q_owner.name AS question_owner_name,
            a.text AS answer_text,
            a_owner.name AS answer_owner_name
        FROM topics t
        LEFT JOIN talks talk ON t.topic_id = talk.topic_id
        LEFT JOIN users talk_owner ON talk.owner_user_id = talk_owner.user_id
        LEFT JOIN questions q ON t.topic_id = q.topic_id
        LEFT JOIN users q_owner ON q.owner_user_id = q_owner.user_id
        LEFT JOIN answers a ON t.topic_id = a.topic_id
        LEFT JOIN users a_owner ON a.owner_user_id = a_owner.user_id
        WHERE t.group_id = ?
          AND t.create_time >= ?
          AND t.create_time < ?
        ORDER BY t.create_time ASC
        """,
        (group_id, start_time, end_time),
    ).fetchall()

    topics: List[Dict[str, Any]] = []
    for row in rows:
        topic_id = row["topic_id"]
        comments = conn.execute(
            """
            SELECT c.comment_id, c.text, c.create_time, c.likes_count, c.sticky, u.name AS owner_name
            FROM comments c
            LEFT JOIN users u ON c.owner_user_id = u.user_id
            WHERE c.topic_id = ?
              AND c.group_id = ?
            ORDER BY c.sticky DESC, c.likes_count DESC, c.create_time ASC
            LIMIT ?
            """,
            (topic_id, group_id, comments_per_topic),
        ).fetchall()
        tags = conn.execute(
            """
            SELECT tags.tag_name
            FROM topic_tags tt
            INNER JOIN tags ON tt.tag_id = tags.tag_id
            WHERE tt.topic_id = ?
              AND tt.topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
            ORDER BY tags.tag_name ASC
            """,
            (topic_id, group_id),
        ).fetchall()
        topic_image_rows = conn.execute(
            """
            SELECT
                image_id, thumbnail_url, thumbnail_width, thumbnail_height,
                large_url, large_width, large_height,
                original_url, original_width, original_height, original_size
            FROM images
            WHERE topic_id = ? AND comment_id IS NULL
              AND topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
            ORDER BY image_id ASC
            LIMIT ?
            """,
            (topic_id, group_id, MAX_IMAGES_PER_TOPIC),
        ).fetchall()

        comment_ids = [comment["comment_id"] for comment in comments]
        comment_images_map: Dict[int, List[Dict[str, Any]]] = {}
        if comment_ids:
            placeholders = ",".join("?" for _ in comment_ids)
            comment_image_rows = conn.execute(
                f"""
                SELECT
                    comment_id, image_id, thumbnail_url, thumbnail_width, thumbnail_height,
                    large_url, large_width, large_height,
                    original_url, original_width, original_height, original_size
                FROM images
                WHERE comment_id IN ({placeholders})
                  AND topic_id IN (SELECT topic_id FROM topics WHERE group_id = ?)
                ORDER BY comment_id ASC, image_id ASC
                """,
                [*comment_ids, group_id],
            ).fetchall()
            for image_index, image_row in enumerate(comment_image_rows, start=1):
                comment_id = image_row["comment_id"]
                images = comment_images_map.setdefault(comment_id, [])
                if len(images) < MAX_IMAGES_PER_TOPIC:
                    images.append(_image_row_to_payload(image_row, f"topic_{topic_id}_comment_{comment_id}_image_{image_index}"))

        topic_images = [
            _image_row_to_payload(image_row, f"topic_{topic_id}_image_{index}")
            for index, image_row in enumerate(topic_image_rows, start=1)
        ]

        topics.append(
            {
                "topic_id": topic_id,
                "type": row["type"],
                "title": row["title"] or "",
                "create_time": row["create_time"],
                "author": row["talk_owner_name"] or row["question_owner_name"] or row["answer_owner_name"] or "",
                "metrics": {
                    "likes_count": row["likes_count"] or 0,
                    "comments_count": row["comments_count"] or 0,
                    "reading_count": row["reading_count"] or 0,
                    "readers_count": row["readers_count"] or 0,
                    "digested": bool(row["digested"]),
                    "sticky": bool(row["sticky"]),
                },
                "tags": [tag["tag_name"] for tag in tags],
                "talk_text": _clip(row["talk_text"], MAX_TOPIC_CHARS),
                "question_text": _clip(row["question_text"], MAX_TOPIC_CHARS),
                "answer_text": _clip(row["answer_text"], MAX_TOPIC_CHARS),
                "images": topic_images,
                "comments": [
                    {
                        "owner": comment["owner_name"] or "",
                        "text": _clip(comment["text"], 1200),
                        "likes_count": comment["likes_count"] or 0,
                        "sticky": bool(comment["sticky"]),
                        "create_time": comment["create_time"],
                        "images": comment_images_map.get(comment["comment_id"], []),
                    }
                    for comment in comments
                    if str(comment["text"] or "").strip() or comment_images_map.get(comment["comment_id"])
                ],
            }
        )
    return topics


def _build_prompt_payload(group_id: str, report_date: str, topics: List[Dict[str, Any]]) -> str:
    payload = {
        "group_id": group_id,
        "report_date": report_date,
        "topic_count": len(topics),
        "topics": topics,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return _clip(text, MAX_PROMPT_CHARS)


def _build_empty_report_summary(report_date: str) -> str:
    return (
        "# 每日话题分析报告\n\n"
        f"日期：{report_date}\n\n"
        "当天没有采集到话题。建议先确认当天最新数据已完成抓取，或检查群组是否确实无新增内容。\n"
    )


def _build_report_metadata(
    *,
    group_id: str,
    report_date: str,
    topics: List[Dict[str, Any]],
    report_path: str,
) -> Dict[str, Any]:
    return {
        "group_id": group_id,
        "report_date": report_date,
        "topic_count": len(topics),
        "topic_ids": [topic["topic_id"] for topic in topics],
        "image_refs": [image["image_ref"] for image in _collect_report_images(topics)],
        "report_path": report_path,
    }


def _parse_report_raw_json(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _collect_report_images(topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []
    for topic in topics:
        for image in topic.get("images", []) or []:
            if image.get("url"):
                images.append(image)
                if len(images) >= MAX_IMAGES_PER_REPORT:
                    return images

        for comment in topic.get("comments", []) or []:
            for image in comment.get("images", []) or []:
                if image.get("url"):
                    images.append(image)
                    if len(images) >= MAX_IMAGES_PER_REPORT:
                        return images
    return images


def _build_image_content_parts(group_id: str, images: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    cache_manager = get_image_cache_manager(group_id)
    content_parts: List[Dict[str, str]] = []
    for image in images:
        url = str(image.get("url") or "").strip()
        if not url:
            continue

        success, cache_path, _error = cache_manager.download_and_cache(url, timeout=15)
        if not success or not cache_path or not cache_path.exists():
            continue
        if cache_path.stat().st_size > MAX_IMAGE_BYTES:
            continue

        mime_type = mimetypes.guess_type(str(cache_path))[0] or "image/jpeg"
        encoded = base64.b64encode(cache_path.read_bytes()).decode("ascii")
        content_parts.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
            }
        )
    return content_parts


def _extract_response_text(response: Any) -> str:
    text_value = getattr(response, "output_text", None)
    if text_value:
        return str(text_value)

    outputs = getattr(response, "output", []) or []
    chunks = []
    for output in outputs:
        for content in getattr(output, "content", []) or []:
            chunk_text = getattr(content, "text", None)
            if chunk_text:
                chunks.append(str(chunk_text))
    return "\n".join(chunks)


def _generate_report_with_ai(
    prompt_payload: str,
    report_date: str,
    *,
    group_id: str,
    image_inputs: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    runtime_ai_config = get_openai_compatible_config()
    api_key = str(runtime_ai_config.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and config.toml [ai].api_key is empty")

    model = str(runtime_ai_config.get("model") or get_default_model())
    api_base = str(runtime_ai_config.get("base_url") or get_default_base_url())
    wire_api = str(runtime_ai_config.get("wire_api") or get_default_wire_api())
    reasoning_effort = get_summary_reasoning_effort()

    image_inputs = image_inputs or []
    image_refs = [str(image.get("image_ref") or "") for image in image_inputs if image.get("image_ref")]
    image_note = ""
    if image_refs:
        image_note = (
            "\n- 部分话题图片已作为附件随本请求传入；图片顺序与话题数据中的 image_ref 顺序一致。"
            "\n- 如图片内容影响判断，请在相关话题分析中结合文字与图片，不要臆测图片外的信息。"
        )

    user_prompt = (
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

    messages = [
        {
            "role": "system",
            "content": (
                "你是知识星球社群日报分析助手。"
                "请只基于输入的话题数据分析，不要编造未出现的信息。"
                "输出中文 Markdown，重点给群主/运营者可执行的信息密度。"
            ),
        },
    ]

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=180)
    if wire_api.strip().lower() == "responses":
        user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
        user_content.extend(_build_image_content_parts(group_id, image_inputs))
        messages.append({"role": "user", "content": user_content})
        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": reasoning_effort},
        )
        return _extract_response_text(response).strip(), model

    user_content = [{"type": "text", "text": user_prompt}]
    for image_part in _build_image_content_parts(group_id, image_inputs):
        user_content.append({"type": "image_url", "image_url": {"url": image_part["image_url"]}})
    messages.append({"role": "user", "content": user_content if len(user_content) > 1 else user_prompt})
    response = client.chat.completions.create(model=model, messages=messages, stream=False)
    return str(response.choices[0].message.content or "").strip(), model


def _write_report_file(group_id: str, report_date: str, summary_markdown: str) -> str:
    group_dir = Path(get_db_path_manager().get_group_dir(group_id))
    report_dir = group_dir / "daily_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{report_date}.md"
    report_path.write_text(summary_markdown, encoding="utf-8")
    return str(report_path)


def analyze_daily_topics(
    group_id: str,
    report_date: Optional[str] = None,
    *,
    comments_per_topic: int = DEFAULT_COMMENTS_PER_TOPIC,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Generate and persist one daily AI topic report."""
    parsed_date = _parse_report_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = _connect_topics_db(group_id)

    try:
        _log(log_callback, f"📚 读取 {report_date_text} 的话题数据...")
        topics = _fetch_topics_for_date(
            conn,
            group_id=group_id,
            report_date=parsed_date,
            comments_per_topic=comments_per_topic,
        )
        topic_count = len(topics)
        _log(log_callback, f"📊 当天话题数量: {topic_count}")

        if topic_count == 0:
            summary = _build_empty_report_summary(report_date_text)
            model = ""
        else:
            prompt_payload = _build_prompt_payload(group_id, report_date_text, topics)
            image_inputs = _collect_report_images(topics)
            if image_inputs:
                _log(log_callback, f"🖼️ 将随日报传入 {len(image_inputs)} 张话题图片附件")
            _log(log_callback, "🤖 正在调用 AI 生成日报...")
            summary, model = _generate_report_with_ai(
                prompt_payload,
                report_date_text,
                group_id=group_id,
                image_inputs=image_inputs,
            )
            if not summary:
                raise RuntimeError("AI 返回内容为空")

        report_path = _write_report_file(group_id, report_date_text, summary)
        raw_json = _build_report_metadata(
            group_id=group_id,
            report_date=report_date_text,
            topics=topics,
            report_path=report_path,
        )
        _upsert_report(
            conn,
            group_id=group_id,
            report_date=report_date_text,
            topic_count=topic_count,
            model=model,
            summary_markdown=summary,
            raw_json=raw_json,
            status="completed",
        )
        _log(log_callback, f"✅ 日报已生成: {report_path}")
        return {
            "group_id": group_id,
            "report_date": report_date_text,
            "topic_count": topic_count,
            "model": model,
            "summary_markdown": summary,
            "report_path": report_path,
        }
    except Exception as exc:
        _upsert_report(
            conn,
            group_id=group_id,
            report_date=report_date_text,
            topic_count=0,
            model=str(get_openai_compatible_config().get("model") or ""),
            summary_markdown="",
            raw_json={"group_id": group_id, "report_date": report_date_text},
            status="failed",
            error=str(exc),
        )
        raise
    finally:
        conn.close()


def get_daily_report(group_id: str, report_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    parsed_date = _parse_report_date(report_date)
    report_date_text = parsed_date.isoformat()
    conn = _connect_topics_db(group_id)
    try:
        row = conn.execute(
            """
            SELECT group_id, report_date, topic_count, model, prompt_version,
                   summary_markdown, raw_json, status, error, created_at, updated_at
            FROM daily_ai_reports
            WHERE group_id = ? AND report_date = ?
            """,
            (group_id, report_date_text),
        ).fetchone()
        if not row:
            return None
        raw_json = _parse_report_raw_json(row["raw_json"])
        return {
            "group_id": row["group_id"],
            "report_date": row["report_date"],
            "topic_count": row["topic_count"],
            "model": row["model"],
            "prompt_version": row["prompt_version"],
            "summary_markdown": row["summary_markdown"],
            "raw_json": raw_json,
            "status": row["status"],
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()
