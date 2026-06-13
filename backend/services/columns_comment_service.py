from __future__ import annotations

import json
from typing import Any, Callable, Dict

import requests
from fastapi import HTTPException

from backend.core.account_context import build_stealth_headers
from backend.core.logger_config import log_debug, log_error, log_info
from backend.services.columns_remote_service import redact_response_for_log
from backend.storage.accounts_sql_manager import get_accounts_sql_manager
from backend.storage.zsxq_columns_database import ZSXQColumnsDatabase


def _process_column_comment(comment: Dict[str, Any]) -> Dict[str, Any]:
    processed: Dict[str, Any] = {
        "comment_id": comment.get("comment_id"),
        "parent_comment_id": comment.get("parent_comment_id"),
        "text": comment.get("text", ""),
        "create_time": comment.get("create_time"),
        "likes_count": comment.get("likes_count", 0),
        "rewards_count": comment.get("rewards_count", 0),
        "replies_count": comment.get("replies_count", 0),
        "sticky": comment.get("sticky", False),
        "owner": comment.get("owner"),
        "repliee": comment.get("repliee"),
        "images": comment.get("images", []),
    }

    replied_comments = comment.get("replied_comments", [])
    if replied_comments:
        processed["replied_comments"] = [
            {
                "comment_id": reply.get("comment_id"),
                "parent_comment_id": reply.get("parent_comment_id"),
                "text": reply.get("text", ""),
                "create_time": reply.get("create_time"),
                "likes_count": reply.get("likes_count", 0),
                "owner": reply.get("owner"),
                "repliee": reply.get("repliee"),
                "images": reply.get("images", []),
            }
            for reply in replied_comments
        ]

    return processed


def fetch_column_topic_full_comments(
    group_id: str,
    topic_id: int,
    *,
    columns_db_factory: Callable[[str], ZSXQColumnsDatabase] = ZSXQColumnsDatabase,
    request_get: Callable[..., Any] = requests.get,
) -> Dict[str, Any]:
    manager = get_accounts_sql_manager()
    account = manager.get_account_for_group(group_id, mask_cookie=False)
    if not account or not account.get("cookie"):
        raise HTTPException(status_code=400, detail="No valid account found for this group")

    headers = build_stealth_headers(account["cookie"])
    comments_url = f"https://api.zsxq.com/v2/topics/{topic_id}/comments?sort=asc&count=30&with_sticky=true"
    log_info(f"Fetching comments from: {comments_url}")
    resp = request_get(comments_url, headers=headers, timeout=30)

    if resp.status_code != 200:
        log_error(f"Failed to fetch comments: HTTP {resp.status_code}, response={redact_response_for_log(resp.text)}")
        raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch comments: HTTP {resp.status_code}")

    data = resp.json()
    log_debug(
        "Comments API response: "
        f"succeeded={data.get('succeeded')}, "
        f"resp_data keys={list(data.get('resp_data', {}).keys()) if data.get('resp_data') else 'None'}"
    )

    if not data.get("succeeded"):
        resp_data = data.get("resp_data", {})
        error_msg = resp_data.get("message") or resp_data.get("error_msg") or data.get("error_msg") or data.get("message")
        error_code = resp_data.get("code") or resp_data.get("error_code") or data.get("code")
        log_error(f"Comments API failed: code={error_code}, message={error_msg}, full_response={json.dumps(data, ensure_ascii=False)[:500]}")
        raise HTTPException(status_code=400, detail=f"API error: {error_msg or 'Request failed'} (code: {error_code})")

    processed_comments = [
        _process_column_comment(comment)
        for comment in data.get("resp_data", {}).get("comments", [])
    ]

    try:
        db = columns_db_factory(group_id)
        try:
            saved_count = db.import_comments(topic_id, processed_comments)
        finally:
            db.close()
        log_info(f"Saved {saved_count} comments to database for topic {topic_id}")
    except Exception as exc:
        log_error(f"Failed to save comments to database: {exc}")

    total_count = sum(1 + len(comment.get("replied_comments", [])) for comment in processed_comments)

    return {
        "success": True,
        "comments": processed_comments,
        "total": total_count,
    }
