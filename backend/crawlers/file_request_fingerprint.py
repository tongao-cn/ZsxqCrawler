"""Request fingerprint helpers for ZSXQ file crawler traffic."""

from __future__ import annotations

from typing import Any, Dict, Optional


STEALTH_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
)
STEALTH_ACCEPT_LANGUAGES = (
    'zh-CN,zh;q=0.9,en;q=0.8',
    'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
    'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
)
STEALTH_PLATFORMS = ('"Windows"', '"macOS"', '"Linux"')
STEALTH_OPTIONAL_HEADERS = (
    ('DNT', '1'),
    ('Sec-GPC', '1'),
    ('Upgrade-Insecure-Requests', '1'),
    ('X-Requested-With', 'XMLHttpRequest'),
)


def stealth_user_agents() -> list[str]:
    return list(STEALTH_USER_AGENTS)


def stealth_accept_languages() -> list[str]:
    return list(STEALTH_ACCEPT_LANGUAGES)


def stealth_platforms() -> list[str]:
    return list(STEALTH_PLATFORMS)


def stealth_optional_headers() -> Dict[str, str]:
    return dict(STEALTH_OPTIONAL_HEADERS)


def stealth_timestamp_header_value(current_time: int, offset_seconds: int) -> str:
    return str(current_time + offset_seconds)


def stealth_request_id_header_value(request_id: int) -> str:
    return f"req-{request_id}"


def stealth_base_headers(
    cookie: str,
    group_id: Any,
    selected_ua: str,
    sec_ch_ua: str,
    accept_language: str,
    platform: str,
) -> Dict[str, str]:
    return {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': accept_language,
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Cookie': cookie,
        'Host': 'api.zsxq.com',
        'Origin': 'https://wx.zsxq.com',
        'Pragma': 'no-cache',
        'Referer': f'https://wx.zsxq.com/dweb2/index/group/{group_id}',
        'Sec-Ch-Ua': sec_ch_ua,
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': platform,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'User-Agent': selected_ua,
    }


def risk_event_user_agent_label(user_agent: str) -> str:
    text = str(user_agent or "")
    browser = "Other"
    if "Edg/" in text:
        browser = "Edge"
    elif "Chrome/" in text or "Chromium/" in text:
        browser = "Chrome"
    elif "Firefox/" in text:
        browser = "Firefox"
    elif "Safari/" in text:
        browser = "Safari"

    platform = "Other"
    if "Windows" in text:
        platform = "Windows"
    elif "Macintosh" in text or "Mac OS X" in text:
        platform = "Mac"
    elif "Linux" in text or "X11" in text:
        platform = "Linux"
    elif "Android" in text:
        platform = "Android"
    elif "iPhone" in text or "iPad" in text:
        platform = "iOS"

    return f"{browser} {platform}"


def risk_event_header_profile_label(headers: Dict[str, str]) -> str:
    normalized = {str(key).lower(): value for key, value in (headers or {}).items()}
    labels = []
    if "referer" in normalized:
        labels.append("referer")
    if "origin" in normalized:
        labels.append("origin")
    if any(key.startswith("sec-fetch-") for key in normalized):
        labels.append("sec-fetch")
    if any(key.startswith("sec-ch-") for key in normalized):
        labels.append("sec-ch")
    if "x-timestamp" in normalized:
        labels.append("x-timestamp")
    if "x-request-id" in normalized:
        labels.append("x-request-id")
    return "+".join(labels) or "minimal"


def risk_event_header_user_agent(headers: Optional[Dict[str, str]]) -> str:
    if not headers:
        return ""
    return headers.get("User-Agent") or headers.get("user-agent") or ""


def risk_event_row(
    timestamp: str,
    group_id: Any,
    file_id: int,
    phase: str,
    attempt: int = 0,
    headers: Optional[Dict[str, str]] = None,
    http_status: Optional[int] = None,
    api_code: Optional[Any] = None,
    api_message: Optional[str] = None,
    status: str = "observed",
) -> Dict[str, Any]:
    user_agent = risk_event_header_user_agent(headers)
    return {
        "timestamp": timestamp,
        "group_id": group_id,
        "file_id": file_id,
        "phase": phase,
        "attempt": attempt,
        "ua_label": risk_event_user_agent_label(user_agent),
        "header_profile": risk_event_header_profile_label(headers or {}),
        "status": status,
        "http_status": "" if http_status is None else http_status,
        "api_code": "" if api_code is None else api_code,
        "api_message": api_message or "",
    }


def sec_ch_ua_for_user_agent(user_agent: str) -> str:
    if "Chrome" in user_agent:
        if "131.0.0.0" in user_agent:
            return '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
        if "130.0.0.0" in user_agent:
            return '"Google Chrome";v="130", "Chromium";v="130", "Not?A_Brand";v="99"'
        if "129.0.0.0" in user_agent:
            return '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"'
        return '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
    return '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'


__all__ = [
    "STEALTH_ACCEPT_LANGUAGES",
    "STEALTH_OPTIONAL_HEADERS",
    "STEALTH_PLATFORMS",
    "STEALTH_USER_AGENTS",
    "risk_event_header_profile_label",
    "risk_event_header_user_agent",
    "risk_event_row",
    "risk_event_user_agent_label",
    "sec_ch_ua_for_user_agent",
    "stealth_accept_languages",
    "stealth_base_headers",
    "stealth_optional_headers",
    "stealth_platforms",
    "stealth_request_id_header_value",
    "stealth_timestamp_header_value",
    "stealth_user_agents",
]
