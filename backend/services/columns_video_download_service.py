from __future__ import annotations

import asyncio
import os
import queue
import subprocess
import threading
import time
from typing import Any, Callable

import requests

from backend.services.columns_remote_service import redact_response_for_log, retry_wait_seconds


async def download_column_video(
    *,
    add_task_log: Callable[[str, str], None] = lambda _task_id, _message: None,
    db: Any,
    group_dir: str,
    headers: dict,
    log_error: Callable[[str], None] = lambda _message: None,
    log_exception: Callable[[str], None] = lambda _message: None,
    log_info: Callable[[str], None] = lambda _message: None,
    request_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], Any] = asyncio.sleep,
    task_id: str | None = None,
    video_duration: int,
    video_id: int,
    video_size: int,
    topic_id: int,
) -> str:
    videos_dir = os.path.join(group_dir, "column_videos")
    video_filename = f"video_{video_id}.mp4"
    local_path = os.path.join(videos_dir, video_filename)

    if os.path.exists(local_path):
        existing_size = os.path.getsize(local_path)
        if existing_size > 0:
            db.update_video_download_status(video_id, "completed", "", local_path)
            if task_id:
                add_task_log(task_id, f"         ⏭️ 视频已存在，跳过下载 ({existing_size/(1024*1024):.1f}MB)")
            return "skipped"

    video_url_api = f"https://api.zsxq.com/v2/videos/{video_id}/url"
    max_retries = 10
    m3u8_url = None

    for retry in range(max_retries):
        try:
            resp = request_get(video_url_api, headers=headers, timeout=30)
        except Exception as req_err:
            if retry < max_retries - 1:
                await sleep(retry_wait_seconds(retry))
                continue
            log_exception(f"获取视频链接请求异常: video_id={video_id}")
            raise Exception(f"获取视频链接请求异常: {req_err}")

        if resp.status_code != 200:
            if retry < max_retries - 1:
                await sleep(retry_wait_seconds(retry))
                continue
            error_msg = f"获取视频链接失败: HTTP {resp.status_code}, URL={video_url_api}, Response={redact_response_for_log(resp.text)}"
            log_error(error_msg)
            raise Exception(error_msg)

        data = resp.json()
        if not data.get("succeeded"):
            error_code = data.get("code")
            error_message = data.get("error_message", "未知错误")

            if error_code == 1059:
                if retry < max_retries - 1:
                    await sleep(retry_wait_seconds(retry))
                    continue
                log_error(f"获取视频链接重试{max_retries}次后仍失败: video_id={video_id}, code={error_code}")
                raise Exception(f"获取视频链接失败，重试{max_retries}次后仍遇到反爬限制")

            error_msg = f"获取视频链接失败: code={error_code}, message={error_message}, video_id={video_id}, topic_id={topic_id}"
            log_error(error_msg)
            raise Exception(f"获取视频链接失败: {error_message} (code={error_code})")

        m3u8_url = data.get("resp_data", {}).get("url")
        break

    if not m3u8_url:
        raise Exception("视频链接为空")

    os.makedirs(videos_dir, exist_ok=True)
    db.update_video_download_status(video_id, "downloading", m3u8_url)

    try:
        ffmpeg_check = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if ffmpeg_check.returncode != 0:
            raise Exception("ffmpeg not available")

        ffmpeg_headers = ""
        if headers.get("Cookie"):
            ffmpeg_headers += f"Cookie: {headers['Cookie']}\r\n"
        if headers.get("cookie"):
            ffmpeg_headers += f"Cookie: {headers['cookie']}\r\n"
        ffmpeg_headers += "Referer: https://wx.zsxq.com/\r\n"
        ffmpeg_headers += "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
        ffmpeg_headers += "Origin: https://wx.zsxq.com\r\n"

        cmd = [
            "ffmpeg", "-y",
            "-headers", ffmpeg_headers,
            "-i", m3u8_url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-progress", "pipe:1",
            local_path,
        ]

        log_info(f"开始下载视频: video_id={video_id}, url={m3u8_url[:100]}...")
        if task_id:
            add_task_log(task_id, f"         🎬 开始下载视频 (预计时长: {video_duration}秒, 大小: {video_size/(1024*1024):.1f}MB)")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stderr_output = []
        stdout_queue = queue.Queue()

        def read_stdout():
            try:
                for line in iter(process.stdout.readline, ""):
                    if line:
                        stdout_queue.put(line)
                    if process.poll() is not None:
                        break
            except Exception:
                pass

        def read_stderr():
            try:
                for line in iter(process.stderr.readline, ""):
                    if line:
                        stderr_output.append(line)
            except Exception:
                pass

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        last_log_time = time.time()
        start_time = time.time()

        try:
            while process.poll() is None:
                try:
                    line = stdout_queue.get(timeout=1)
                    if line.startswith("out_time_ms="):
                        try:
                            time_ms = int(line.split("=")[1].strip())
                            current_seconds = time_ms / 1000000
                            now = time.time()
                            if task_id and (now - last_log_time) >= 3:
                                if video_duration > 0:
                                    progress_pct = min(100, (current_seconds / video_duration) * 100)
                                    bar_length = 20
                                    filled = int(bar_length * progress_pct / 100)
                                    bar = "█" * filled + "░" * (bar_length - filled)
                                    add_task_log(task_id, f"         📊 下载进度: [{bar}] {progress_pct:.1f}% ({current_seconds:.0f}s/{video_duration}s)")
                                else:
                                    add_task_log(task_id, f"         📊 下载进度: {current_seconds:.0f}秒")
                                last_log_time = now
                        except Exception:
                            pass
                except queue.Empty:
                    now = time.time()
                    elapsed = now - start_time
                    if task_id and (now - last_log_time) >= 5:
                        add_task_log(task_id, f"         ⏳ 下载中... (已用时 {elapsed:.0f}秒)")
                        last_log_time = now
                    continue

            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
        except Exception as exc:
            process.kill()
            raise Exception(f"视频下载异常: {exc}")

        returncode = process.returncode
        stderr_text = "".join(stderr_output)

        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            db.update_video_download_status(video_id, "completed", m3u8_url, local_path)
            final_size = os.path.getsize(local_path)
            log_info(f"视频下载成功: video_id={video_id}, path={local_path}, size={final_size}")
            if task_id:
                add_task_log(task_id, f"         ✅ 视频下载完成 ({final_size/(1024*1024):.1f}MB)")
            return "downloaded"

        db.update_video_download_status(video_id, "failed", m3u8_url)
        stderr_lines = stderr_text.strip().split("\n")
        error_lines = [
            line
            for line in stderr_lines
            if "error" in line.lower() or "failed" in line.lower() or "invalid" in line.lower()
        ]
        if error_lines:
            error_msg = "; ".join(error_lines[-3:])
        else:
            error_msg = "; ".join(stderr_lines[-3:]) if stderr_lines else "unknown error"
        log_error(f"ffmpeg下载失败: video_id={video_id}, returncode={returncode}, error={error_msg}")
        raise Exception(f"ffmpeg下载失败: {error_msg[:300]}")

    except FileNotFoundError:
        db.update_video_download_status(video_id, "pending_manual", m3u8_url)
        m3u8_link_file = os.path.join(videos_dir, f"video_{video_id}.m3u8.txt")
        with open(m3u8_link_file, "w", encoding="utf-8") as file_obj:
            file_obj.write(f"Video ID: {video_id}\n")
            file_obj.write(f"Duration: {video_duration} seconds\n")
            file_obj.write(f"Size: {video_size} bytes\n")
            file_obj.write(f"M3U8 URL: {m3u8_url}\n")
        raise Exception("ffmpeg未安装，已保存m3u8链接到文件，请手动下载")
    except subprocess.TimeoutExpired:
        db.update_video_download_status(video_id, "failed", m3u8_url)
        raise Exception("视频下载超时")
