from __future__ import annotations

from typing import Callable

from backend.core.image_cache_manager import clear_group_cache_manager, get_image_cache_manager


def clear_group_image_cache(group_id: str, log_event: Callable[[str, str], None]) -> None:
    try:
        cache_manager = get_image_cache_manager(group_id)
        success, message = cache_manager.clear_cache()
        if success:
            log_event("INFO", f"图片缓存已清空: {message}")
        else:
            log_event("WARN", f"清空图片缓存失败: {message}")
        clear_group_cache_manager(group_id)
    except Exception as cache_error:
        log_event("WARN", f"清空图片缓存时出错: {cache_error}")
