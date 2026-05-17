from __future__ import annotations

from pathlib import Path


TARGET = Path(r"C:\Dev\ZsxqCrawler\docs\xmind\光模块.txt")


def main() -> None:
    records = []
    for raw in TARGET.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        depth = len(raw) - len(raw.lstrip("\t"))
        name = raw.strip()
        records.append((depth, name))

    need = {
        "一句话总结",
        "业务构成和客户分布",
        "事件驱动",
        "前瞻市值/收入/利润/目标价",
    }

    company_nodes = []
    for idx, (depth, name) in enumerate(records):
        children = []
        j = idx + 1
        while j < len(records) and records[j][0] > depth:
            if records[j][0] == depth + 1:
                children.append(records[j][1])
            j += 1
        if need.issubset(children):
            company_nodes.append((depth, name, children))

    issues = []
    for depth, name, children in company_nodes:
        if len(children) != 4:
            issues.append((name, depth, children))

    print(f"records={len(records)}")
    print(f"company_nodes={len(company_nodes)}")
    print(f"issues={len(issues)}")
    for item in issues[:10]:
        print(item)


if __name__ == "__main__":
    main()
