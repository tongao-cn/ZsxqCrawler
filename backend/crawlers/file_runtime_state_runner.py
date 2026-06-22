"""Runtime stop and delay runner for ZSXQ file downloads."""

from __future__ import annotations

import datetime
import random
import time
from typing import Any, Callable, Optional, Protocol

from backend.core.console_output import safe_console_print as print
from backend.crawlers.zsxq_file_downloader_targets import (
    CheckLongDelayTarget,
    CheckStopTarget,
    DownloadDelayTarget,
    IsStoppedTarget,
    SetStopFlagTarget,
    SmartDelayTarget,
)


class RuntimeState(Protocol):
    stop_flag: bool
    stop_check_func: Optional[Callable[[], bool]]
    min_delay: float
    max_delay: float
    debug_mode: bool
    use_random_interval: bool
    download_interval: float
    download_interval_min: float
    download_interval_max: float
    download_count: int
    long_delay_interval: int
    long_sleep_interval: float
    long_sleep_interval_min: float
    long_sleep_interval_max: float

    def log(self, message: str) -> None:
        ...

    def is_stopped(self) -> Any:
        ...


def set_stop_flag_target(runtime: RuntimeState, target: SetStopFlagTarget) -> None:
    runtime.stop_flag = True
    runtime.log("🛑 收到停止信号，任务将在下一个检查点停止")


def set_stop_flag(runtime: RuntimeState) -> None:
    return set_stop_flag_target(runtime, SetStopFlagTarget())


def is_stopped_target(runtime: RuntimeState, target: IsStoppedTarget) -> bool:
    if runtime.stop_flag:
        return True
    if runtime.stop_check_func and runtime.stop_check_func():
        runtime.stop_flag = True
        return True
    return False


def is_stopped(runtime: RuntimeState) -> bool:
    return is_stopped_target(runtime, IsStoppedTarget())


def check_stop_target(runtime: RuntimeState, target: CheckStopTarget) -> Any:
    return runtime.is_stopped()


def check_stop(runtime: RuntimeState) -> Any:
    return check_stop_target(runtime, CheckStopTarget())


def smart_delay_target(runtime: RuntimeState, target: SmartDelayTarget) -> None:
    delay = random.uniform(runtime.min_delay, runtime.max_delay)
    if runtime.debug_mode:
        print(f"   ⏱️ 延迟 {delay:.1f}秒")
    time.sleep(delay)


def smart_delay(runtime: RuntimeState) -> None:
    return smart_delay_target(runtime, SmartDelayTarget())


def download_delay_target(runtime: RuntimeState, target: DownloadDelayTarget) -> None:
    if runtime.use_random_interval:
        delay = random.uniform(runtime.download_interval_min, runtime.download_interval_max)
        print(f"⏳ 下载间隔: {delay:.0f}秒 ({delay/60:.1f}分钟) [随机范围: {runtime.download_interval_min}-{runtime.download_interval_max}秒]")
    else:
        delay = runtime.download_interval
        print(f"⏳ 下载间隔: {delay:.1f}秒 [固定间隔]")

    start_time = datetime.datetime.now()
    end_time = start_time + datetime.timedelta(seconds=delay)

    print(f"   ⏰ 开始时间: {start_time.strftime('%H:%M:%S')}")
    print(f"   🕐 预计恢复: {end_time.strftime('%H:%M:%S')}")

    time.sleep(delay)

    actual_end_time = datetime.datetime.now()
    print(f"   🕐 实际结束: {actual_end_time.strftime('%H:%M:%S')}")


def download_delay(runtime: RuntimeState) -> None:
    return download_delay_target(runtime, DownloadDelayTarget())


def check_long_delay_target(runtime: RuntimeState, target: CheckLongDelayTarget) -> None:
    if runtime.download_count > 0 and runtime.download_count % runtime.long_delay_interval == 0:
        if runtime.use_random_interval:
            delay = random.uniform(runtime.long_sleep_interval_min, runtime.long_sleep_interval_max)
            print(f"🛌 长休眠开始: {delay:.0f}秒 ({delay/60:.1f}分钟) [随机范围: {runtime.long_sleep_interval_min/60:.1f}-{runtime.long_sleep_interval_max/60:.1f}分钟]")
        else:
            delay = runtime.long_sleep_interval
            print(f"🛌 长休眠开始: {delay:.0f}秒 ({delay/60:.1f}分钟) [固定间隔]")

        start_time = datetime.datetime.now()
        end_time = start_time + datetime.timedelta(seconds=delay)

        print(f"   已下载 {runtime.download_count} 个文件，进入长休眠模式...")
        print(f"   ⏰ 开始时间: {start_time.strftime('%H:%M:%S')}")
        print(f"   🕐 预计恢复: {end_time.strftime('%H:%M:%S')}")

        time.sleep(delay)

        actual_end_time = datetime.datetime.now()
        print("😴 长休眠结束，继续下载...")
        print(f"   🕐 实际结束: {actual_end_time.strftime('%H:%M:%S')}")


def check_long_delay(runtime: RuntimeState) -> None:
    return check_long_delay_target(runtime, CheckLongDelayTarget())
