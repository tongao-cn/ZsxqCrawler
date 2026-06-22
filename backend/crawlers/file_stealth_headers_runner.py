"""Stealth request header runner for ZSXQ file requests."""

from __future__ import annotations

import random
import time
from typing import Any, Dict, Protocol

from backend.crawlers.zsxq_file_downloader_helpers import (
    sec_ch_ua_for_user_agent,
    stealth_accept_languages,
    stealth_base_headers,
    stealth_optional_headers,
    stealth_platforms,
    stealth_request_id_header_value,
    stealth_timestamp_header_value,
    stealth_user_agents,
)
from backend.crawlers.zsxq_file_downloader_targets import StealthHeaderSelection


class StealthHeadersRuntime(Protocol):
    cookie: str
    group_id: Any


def select_stealth_header_values() -> StealthHeaderSelection:
    user_agents = stealth_user_agents()
    selected_ua = random.choice(user_agents)
    sec_ch_ua = sec_ch_ua_for_user_agent(selected_ua)

    accept_languages = stealth_accept_languages()
    platforms = stealth_platforms()
    accept_language = random.choice(accept_languages)
    platform = random.choice(platforms)

    return StealthHeaderSelection(selected_ua, sec_ch_ua, accept_language, platform)


def apply_optional_stealth_headers(headers: Dict[str, str]) -> None:
    optional_headers = stealth_optional_headers()
    for key, value in optional_headers.items():
        if random.random() > 0.5:
            headers[key] = value


def apply_dynamic_stealth_headers(headers: Dict[str, str]) -> None:
    if random.random() > 0.7:
        headers["X-Timestamp"] = stealth_timestamp_header_value(
            int(time.time()),
            random.randint(-30, 30),
        )

    if random.random() > 0.6:
        headers["X-Request-Id"] = stealth_request_id_header_value(
            random.randint(100000000000, 999999999999),
        )


def get_stealth_headers(runtime: StealthHeadersRuntime) -> Dict[str, str]:
    selection = select_stealth_header_values()
    headers = stealth_base_headers(
        runtime.cookie,
        runtime.group_id,
        selection.user_agent,
        selection.sec_ch_ua,
        selection.accept_language,
        selection.platform,
    )
    apply_optional_stealth_headers(headers)
    apply_dynamic_stealth_headers(headers)
    return headers
