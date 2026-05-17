from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Dev\ZsxqCrawler")
TARGET = ROOT / "docs" / "xmind" / "光模块.txt"
TOPIC_DATA = ROOT / "tmp" / "deep_topics.json"


def N(name: str, *children: Any) -> dict[str, Any]:
    return {"name": name, "children": list(children)}


def strip_alias(name: str) -> str:
    return re.sub(r"（.*?）", "", name).strip()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def one_sentence(text: str) -> str:
    value = norm(text)
    if not value:
        return "无"
    for part in re.split(r"[。！？]\s*", value):
        part = part.strip()
        if part:
            return part + "。"
    return value[:120] + ("…" if len(value) > 120 else "")


def short(text: str, limit: int = 180) -> str:
    value = norm(text)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def focus_name(path: list[str], display_name: str) -> str:
    full = " / ".join(path + [display_name])
    for key, label in [
        ("800G/1.6T/3.2T高速数通光模块", "高速数通光模块"),
        ("CPO/全光互联光引擎", "CPO/全光互联"),
        ("光芯片", "光芯片"),
        ("光材料", "光材料"),
        ("光器件", "光器件"),
        ("光连接与光纤", "光连接与光纤"),
        ("电芯片与测试", "电芯片与测试"),
        ("PCB/封装/设备", "PCB/封装/设备"),
        ("OCS/全光互联", "OCS/全光互联"),
        ("其他元器件", "其他元器件"),
    ]:
        if key in full:
            return label
    return display_name


EVENT_KEYWORDS = (
    "订单", "出货", "放量", "量产", "验证", "送测", "扩产", "涨价", "需求", "合作",
    "突破", "认证", "爬坡", "导入", "扩建", "上修", "景气", "短缺", "预期", "锁定",
    "定调", "落地", "排至", "涨超", "财报", "供需", "产能", "签订",
)

BUSINESS_KEYWORDS = (
    "业务", "客户", "下游", "上游", "布局", "覆盖", "围绕", "主业", "链条", "承接",
    "器件", "模块", "光引擎", "光芯片", "连接", "材料", "光纤", "测试", "封装",
    "电源", "模拟", "晶体", "衬底", "代工", "平台", "工艺", "方案",
)

OUTLOOK_KEYWORDS = (
    "市值", "目标价", "利润", "收入", "估到", "测算", "预测", "万亿", "亿", "2026",
    "2027", "2028", "Q4", "Q3", "Q2", "空间", "目标", "估值", "弹性",
)

BUSINESS_PRODUCT_KEYWORDS = (
    "业务", "产品", "模块", "芯片", "器件", "光引擎", "光纤", "硅光", "CPO", "OCS",
    "FAU", "AWG", "MPO", "封装", "方案", "平台", "路线",
)

BUSINESS_CUSTOMER_KEYWORDS = (
    "客户", "下游", "海外", "大客", "合作", "导入", "验证", "交付", "订单", "供应",
    "英伟达", "NVIDIA", "谷歌", "Google", "Meta", "微软", "亚马逊", "康宁", "Tower", "Cisco", "华为",
)

BUSINESS_CAPACITY_KEYWORDS = (
    "产能", "扩产", "物料", "短缺", "供不应求", "锁定", "排产", "涨价", "供应", "爬坡", "瓶颈", "库存",
)

EVENT_BENEFIT_KEYWORDS = (
    "利好", "上修", "超预期", "大涨", "催化", "突破", "受益", "风口", "景气", "预期",
)

EVENT_ORDER_KEYWORDS = (
    "订单", "出货", "交付", "签订", "签约", "采购", "拿单", "排至", "落地",
)

EVENT_TECH_KEYWORDS = (
    "量产", "验证", "送测", "新产品", "方案", "技术", "CPO", "NPO", "1.6T", "3.2T", "硅光", "光引擎", "COUPE",
)

OUTLOOK_VALUATION_KEYWORDS = (
    "市值", "目标价", "目标市值", "估值", "空间",
)

OUTLOOK_FINANCE_KEYWORDS = (
    "收入", "营收", "利润", "净利", "毛利率", "利润率", "PE", "市盈率", "EPS",
)

OUTLOOK_TIMING_KEYWORDS = (
    "2026", "2027", "2028", "Q2", "Q3", "Q4", "明年", "后年", "年内",
)


def topic_pool(data: dict[str, dict[str, Any]], base_name: str) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in ("调研鹅纪要", "纪要又要"):
        rec = data.get(group, {}).get(base_name)
        if not rec:
            continue
        for topic in rec.get("topics", []):
            title = norm(topic.get("title", ""))
            if not title or title in seen:
                continue
            seen.add(title)
            merged.append(
                {
                    "title": title,
                    "preview": norm(topic.get("preview", "")),
                    "likes_count": int(topic.get("likes_count", 0) or 0),
                    "comments_count": int(topic.get("comments_count", 0) or 0),
                    "reading_count": int(topic.get("reading_count", 0) or 0),
                }
            )
    return merged


def score_topic(topic: dict[str, Any], path: list[str], display_name: str, keywords: tuple[str, ...]) -> int:
    text = topic["title"] + " " + topic["preview"]
    score = sum(1 for kw in keywords if kw in text)
    for part in path + [display_name]:
        if part and part in text:
            score += 2
    score += min(topic.get("reading_count", 0) // 10000, 3)
    score += min(topic.get("comments_count", 0) // 20, 2)
    return score


def select_topics(topics: list[dict[str, Any]], path: list[str], display_name: str, keywords: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        topics,
        key=lambda topic: (
            -score_topic(topic, path, display_name, keywords),
            -topic.get("reading_count", 0),
            -topic.get("comments_count", 0),
            -topic.get("likes_count", 0),
            topic["title"],
        ),
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for topic in ranked:
        if topic["title"] in seen:
            continue
        out.append(topic)
        seen.add(topic["title"])
        if len(out) >= limit:
            break
    return out


def build_summary(display_name: str, base_name: str, path: list[str], topics: list[dict[str, Any]], concepts: list[str]) -> list[str]:
    focus = focus_name(path, display_name)
    head = topics[:2]
    concept_text = "/".join(concepts[:4]) if concepts else "无"
    lines = [
        f"核心判断：{display_name}在{focus}方向的讨论最集中，核心主线围绕{concept_text}展开。",
        f"产业位置：{base_name}如果放回当前光通信链条，主要看{focus}环节的景气传导和订单兑现节奏。",
    ]
    if head:
        lines.append(f"话题锚点：{head[0]['title']}：{one_sentence(head[0]['preview'])}")
    else:
        lines.append("话题锚点：无")
    if len(head) > 1:
        lines.append(f"补充判断：{head[1]['title']}：{one_sentence(head[1]['preview'])}")
    else:
        lines.append("补充判断：无")
    return lines


def build_section(display_name: str, path: list[str], topics: list[dict[str, Any]], keywords: tuple[str, ...], limit: int, fallback: str = "无") -> list[str]:
    selected = select_topics(topics, path, display_name, keywords, limit)
    if not selected:
        return [fallback]
    return [f"{topic['title']}：{short(topic['preview'], 240)}" for topic in selected]


def build_company(display_name: str, path: list[str], data: dict[str, dict[str, Any]], level: int) -> list[str]:
    base_name = strip_alias(display_name)
    topics = topic_pool(data, base_name)
    rec1 = data.get("调研鹅纪要", {}).get(base_name) or {}
    rec2 = data.get("纪要又要", {}).get(base_name) or {}
    concepts = list(dict.fromkeys((rec1.get("concepts") or []) + (rec2.get("concepts") or [])))

    indent = "\t" * level
    child = "\t" * (level + 1)
    lines = [f"{indent}{display_name}"]
    lines.append(f"{child}一句话总结")
    for item in build_summary(display_name, base_name, path, topics, concepts):
        lines.append(f"{child}\t{item}")

    lines.append(f"{child}业务构成和客户分布")
    for sublabel, keywords, limit in [
        ("业务构成", BUSINESS_PRODUCT_KEYWORDS, 3),
        ("客户分布", BUSINESS_CUSTOMER_KEYWORDS, 3),
        ("产能/供应链", BUSINESS_CAPACITY_KEYWORDS, 3),
    ]:
        lines.append(f"{child}\t{sublabel}")
        section = build_section(display_name, path, topics, keywords, limit)
        for item in section:
            lines.append(f"{child}\t\t{item}")

    lines.append(f"{child}事件驱动")
    for sublabel, keywords, limit in [
        ("具体利好", EVENT_BENEFIT_KEYWORDS, 3),
        ("订单/出货", EVENT_ORDER_KEYWORDS, 3),
        ("技术/产品进展", EVENT_TECH_KEYWORDS, 4),
    ]:
        lines.append(f"{child}\t{sublabel}")
        section = build_section(display_name, path, topics, keywords, limit)
        for item in section:
            lines.append(f"{child}\t\t{item}")

    lines.append(f"{child}前瞻市值/收入/利润/目标价")
    for sublabel, keywords, limit in [
        ("市值/估值", OUTLOOK_VALUATION_KEYWORDS, 2),
        ("收入/利润", OUTLOOK_FINANCE_KEYWORDS, 3),
        ("时间/空间", OUTLOOK_TIMING_KEYWORDS, 2),
    ]:
        lines.append(f"{child}\t{sublabel}")
        section = build_section(display_name, path, topics, keywords, limit)
        for item in section:
            lines.append(f"{child}\t\t{item}")
    return lines


TREE = N(
    "光模块",
    N(
        "光模块整机",
        N(
            "800G/1.6T/3.2T高速数通光模块",
            "中际旭创",
            "新易盛",
            "联特科技",
            "华工科技",
            "东山精密（索尔斯）",
            "光迅科技",
            "博创科技",
        ),
        N(
            "CPO/全光互联光引擎",
            "天孚通信",
            "罗博特科",
            "炬光科技",
            "致尚科技",
            "太辰光",
            "长盈通",
        ),
    ),
    N(
        "光芯片",
        N(
            "有源激光器/调制芯片",
            N(
                "EML激光器",
                "源杰科技",
                "长光华芯",
                "华工科技（云岭光电）",
                "东山精密（索尔斯）",
                "光迅科技",
                "众合科技",
            ),
            N(
                "DFB/CW DFB光源",
                "光迅科技（CW光）",
                "仕佳光子",
                "长光华芯",
            ),
            N(
                "VCSEL激光器",
                "长光华芯",
                "纵慧芯光",
            ),
        ),
        N(
            "调制/硅光/TFLN",
            N(
                "硅光芯片",
                "高塔半导体",
                "华为",
                "天孚通信",
                "中际旭创",
            ),
            N(
                "薄膜铌酸锂TFLN",
                "天通股份",
                "济南晶正",
                "福建晶安",
                "安孚科技",
                "易缆微",
            ),
        ),
        N(
            "探测器芯片",
            N("APD/PIN探测器", "长光华芯", "芯片科技"),
        ),
    ),
    N(
        "光材料",
        N(
            "磷化铟/InP衬底",
            "天津凌翔",
            "广东先导（先导稀材）",
            "云南锗业",
            "博杰股份",
            "珠海鼎泰",
        ),
        N(
            "法拉第旋光片/偏振片/隔离器材料",
            "福晶科技",
            "光电股份",
            "新华光",
            "东田微",
            "日月大化",
            "株冶集团",
        ),
        N("铟材料/稀有材料", "株冶集团"),
    ),
    N(
        "光器件",
        N(
            "FAU/光纤阵列/透镜",
            "天孚通信",
            "腾晖光纤",
            "蓝特光学",
            "宇瞳光学",
            "炬光科技",
        ),
        N(
            "AWG/波分/无源器件",
            "仕佳光子",
            "腾景科技",
            "光库科技",
            "大互光",
            "勇创科技",
        ),
        N(
            "MPO/MTP/MMC/SN-MT高密连接器",
            "仕佳光子",
            "光迅科技",
            "光库科技",
            "大互光",
            "勇创科技",
            "太辰光",
        ),
        N(
            "高阶/特种光纤",
            "长盈通",
            "长飞光纤",
            "永鼎光纤",
        ),
    ),
    N(
        "电芯片与测试",
        N(
            "DSP/Driver/TIA/模拟芯片",
            "裕太微",
            "思瑞浦",
            "艾为电子",
            "圣邦股份",
            "杰华特",
            "南芯科技",
        ),
        N(
            "光模块测试设备",
            "鼎阳科技",
            "普源精电",
            "联讯仪器",
            "博杰股份",
        ),
    ),
    N(
        "PCB/封装/设备",
        N(
            "高速PCB/mSAP/RCC/高阶板",
            "胜宏科技",
            "迅捷兴",
            "沪电股份",
            "景旺电子",
            "方正科技",
            "鹏鼎控股",
            "崇达技术",
            "臻鼎-KY",
            "华正新材",
        ),
        N(
            "CPO封装/贴装/自动化设备",
            "罗博特科",
            "FiconTEC",
            "科隆威",
        ),
    ),
    N(
        "OCS/全光互联",
        N("OCS/光交换", "腾景科技", "英唐智控", "赛微电子"),
        N("COUPE/CPO/NPO/OIO", "致尚科技", "天孚通信", "罗博特科", "炬光科技", "太辰光", "华工科技"),
    ),
    N("其他元器件", N("高频晶振/时钟", "泰晶科技")),
)


def render(node: dict[str, Any], data: dict[str, dict[str, Any]], path: list[str] | None = None, level: int = 0) -> list[str]:
    path = path or []
    lines: list[str] = []
    name = node["name"]
    lines.append("\t" * level + name)
    children = node.get("children") or []
    for child in children:
        if isinstance(child, str):
            lines.extend(build_company(child, path + [name], data, level + 1))
        else:
            lines.extend(render(child, data, path + [name], level + 1))
    return lines


def main() -> None:
    data = json.loads(TOPIC_DATA.read_text(encoding="utf-8"))
    lines = render(TREE, data)
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
