from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from backend.core.account_context import get_cookie_for_group
from backend.core.db_path_manager import get_db_path_manager
from backend.crawlers.zsxq_interactive_crawler import ZSXQInteractiveCrawler, load_config


crawler_instance: Optional[ZSXQInteractiveCrawler] = None


def get_crawler(log_callback=None) -> ZSXQInteractiveCrawler:
    global crawler_instance
    if crawler_instance is None:
        config = load_config()
        if not config:
            raise HTTPException(status_code=500, detail="配置文件加载失败")

        auth_config = config.get("auth", {})
        cookie = auth_config.get("cookie", "")
        group_id = auth_config.get("group_id", "")

        if cookie == "your_cookie_here" or group_id == "your_group_id_here" or not cookie or not group_id:
            raise HTTPException(status_code=400, detail="请先在config.toml中配置Cookie和群组ID")

        path_manager = get_db_path_manager()
        db_path = path_manager.get_topics_db_path(group_id)
        crawler_instance = ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)

    return crawler_instance


def get_crawler_for_group(group_id: str, log_callback=None) -> ZSXQInteractiveCrawler:
    config = load_config()
    if not config:
        raise HTTPException(status_code=500, detail="配置文件加载失败")

    cookie = get_cookie_for_group(group_id)
    if not cookie or cookie == "your_cookie_here":
        raise HTTPException(status_code=400, detail="未找到可用Cookie，请先在账号管理或config.toml中配置")

    path_manager = get_db_path_manager()
    db_path = path_manager.get_topics_db_path(group_id)
    return ZSXQInteractiveCrawler(cookie, group_id, db_path, log_callback)


def get_crawler_safe() -> Optional[ZSXQInteractiveCrawler]:
    try:
        return get_crawler()
    except Exception:
        return None


def clear_crawler_instance() -> None:
    global crawler_instance
    crawler_instance = None
