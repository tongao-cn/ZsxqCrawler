from __future__ import annotations

import requests

from backend.core.account_context import build_stealth_headers, get_cookie_for_group


def get_columns_summary(group_id: str) -> dict:
    try:
        cookie = get_cookie_for_group(group_id)

        if not cookie:
            return {
                "has_columns": False,
                "title": None,
                "error": "未找到可用Cookie",
            }

        headers = build_stealth_headers(cookie)
        url = f"https://api.zsxq.com/v2/groups/{group_id}/columns/summary"

        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()
            if data.get("succeeded"):
                resp_data = data.get("resp_data", {})
                return {
                    "has_columns": resp_data.get("has_columns", False),
                    "title": resp_data.get("title", None),
                }
            return {
                "has_columns": False,
                "title": None,
                "error": data.get("error_message", "API返回失败"),
            }
        return {
            "has_columns": False,
            "title": None,
            "error": f"HTTP {response.status_code}",
        }
    except requests.RequestException as e:
        return {
            "has_columns": False,
            "title": None,
            "error": f"网络请求失败: {str(e)}",
        }
    except Exception as e:
        return {
            "has_columns": False,
            "title": None,
            "error": f"获取专栏信息失败: {str(e)}",
        }
