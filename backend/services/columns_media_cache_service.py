from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def cache_topic_images(
    *,
    add_task_log: Callable[[str, str], None] = lambda _task_id, _message: None,
    cache_manager_factory: Callable[[str], Any],
    db: Any,
    group_id: str,
    is_task_stopped: Callable[[str], bool] = lambda _task_id: False,
    log_exception: Callable[[str], None] = lambda _message: None,
    task_id: str,
    topic_detail: Dict[str, Any],
) -> int:
    cached_count = 0
    talk = topic_detail.get("talk", {}) if "talk" in topic_detail else {}
    topic_images = talk.get("images", [])

    for image in topic_images:
        if is_task_stopped(task_id):
            break

        original_url = image.get("original", {}).get("url")
        image_id = image.get("image_id")

        if not original_url or not image_id:
            continue

        try:
            cache_manager = cache_manager_factory(group_id)
            success, local_path, error_msg = cache_manager.download_and_cache(original_url)
            if success and local_path:
                db.update_image_local_path(image_id, str(local_path))
                cached_count += 1
            elif error_msg:
                add_task_log(task_id, f"      ⚠️ 图片缓存失败: {error_msg}")
        except Exception as exc:
            log_exception(f"图片缓存失败: image_id={image_id}, url={original_url}")
            add_task_log(task_id, f"      ⚠️ 图片缓存失败: {exc}")

    return cached_count


def cache_video_cover(
    *,
    add_task_log: Callable[[str, str], None] = lambda _task_id, _message: None,
    cache_manager_factory: Callable[[str], Any],
    cover_url: Optional[str],
    db: Any,
    group_id: str,
    log_exception: Callable[[str], None] = lambda _message: None,
    log_warning: Callable[[str], None] = lambda _message: None,
    task_id: str,
    video_id: int,
) -> bool:
    if not cover_url:
        return False

    try:
        cache_manager = cache_manager_factory(group_id)
        success, cover_local, error_msg = cache_manager.download_and_cache(cover_url)
        if success and cover_local:
            db.update_video_cover_path(video_id, str(cover_local))
            add_task_log(task_id, f"      ✅ 视频封面缓存成功")
            return True
        if error_msg:
            log_warning(f"视频封面缓存失败: video_id={video_id}, url={cover_url}, error={error_msg}")
            add_task_log(task_id, f"      ⚠️ 视频封面缓存失败: {error_msg}")
    except Exception as exc:
        log_exception(f"视频封面缓存失败: video_id={video_id}, url={cover_url}")
        add_task_log(task_id, f"      ⚠️ 视频封面缓存失败: {exc}")

    return False
