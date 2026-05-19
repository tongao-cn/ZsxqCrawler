from __future__ import annotations

import argparse
import csv
import html
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


DEFAULT_CANDIDATES = (
    ("rank_bucket", "rank21_40", 30, "均衡默认: rank21-40 / 30日"),
    ("rank_bucket", "rank21_30", 22, "中等换手: rank21-30 / 22日"),
    ("rank_bucket", "rank56_60", 29, "高收益高换手: rank56-60 / 29日"),
    ("topn", "top50", 26, "TopN保守: Top50 / 26日"),
)


def _float(value: str | None) -> float:
    if value is None or value == "":
        return math.nan
    return float(value)


def _pct(value: float, digits: int = 1) -> str:
    if math.isnan(value):
        return "-"
    return f"{value * 100:.{digits}f}%"


def _display_bucket(bucket: str) -> str:
    if bucket == "all":
        return "All"
    if bucket.startswith("top"):
        return f"Top{bucket[3:]}"
    match = re.match(r"rank(\d+)_(\d+)$", bucket)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return bucket


def _read_summary(path: Path) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            parsed = {
                "family": row["family"],
                "bucket": row["bucket"],
                "window_days": int(row["window_days"]),
                "daily_rows": int(row["daily_rows"]),
                "completed": int(row["completed"]),
                "mean_daily_return": _float(row.get("mean_daily_return")),
                "compound_return": _float(row.get("compound_return")),
                "compound_after_10bps": _float(row.get("compound_after_10bps")),
                "compound_after_20bps": _float(row.get("compound_after_20bps")),
                "compound_after_50bps": _float(row.get("compound_after_50bps")),
                "win_rate": _float(row.get("win_rate")),
                "avg_turnover": _float(row.get("avg_turnover")),
                "max_drawdown_after_10bps": _float(row.get("max_drawdown_after_10bps")),
            }
            by_key[(parsed["family"], parsed["bucket"], parsed["window_days"])] = parsed
    return list(by_key.values())


def _read_monthly_periods(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("period_type") != "month":
                continue
            rows.append(
                {
                    "family": row["family"],
                    "bucket": row["bucket"],
                    "window_days": int(row["window_days"]),
                    "period": row["period"],
                    "compound_return": _float(row.get("compound_return")),
                    "trading_days": int(row.get("trading_days") or 0),
                }
            )
    return rows


def _interpolate(start: tuple[int, int, int], end: tuple[int, int, int], ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    rgb = tuple(round(start[idx] + (end[idx] - start[idx]) * ratio) for idx in range(3))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[idx : idx + 2], 16) / 255 for idx in (0, 2, 4))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _heat_color(value: float, low: float, high: float) -> tuple[str, str]:
    if math.isnan(value):
        return "#f8fafc", "#94a3b8"
    if value >= 0:
        ratio = value / high if high > 0 else 0
        bg = _interpolate((248, 250, 252), (22, 121, 83), ratio)
    else:
        ratio = abs(value) / abs(low) if low < 0 else 0
        bg = _interpolate((248, 250, 252), (185, 28, 28), ratio)
    return bg, "#ffffff" if _luminance(bg) < 0.52 else "#0f172a"


def _render_heatmap(
    title: str,
    note: str,
    rows: list[dict[str, Any]],
    bucket_order: list[str],
    low: float,
    high: float,
) -> str:
    lookup = {(row["bucket"], row["window_days"]): row for row in rows}
    windows = list(range(1, 31))
    head = "".join(f"<th>{day}</th>" for day in windows)
    body: list[str] = []
    for bucket in bucket_order:
        cells: list[str] = []
        for day in windows:
            row = lookup.get((bucket, day))
            if not row:
                cells.append("<td class=\"empty\"></td>")
                continue
            value = row["compound_after_10bps"]
            bg, fg = _heat_color(value, low, high)
            title_text = (
                f"{_display_bucket(bucket)} / {day}日\\n"
                f"10bp后复利收益: {_pct(value, 2)}\\n"
                f"平均换手: {_pct(row['avg_turnover'], 2)}\\n"
                f"胜率: {_pct(row['win_rate'], 2)}\\n"
                f"最大回撤: {_pct(row['max_drawdown_after_10bps'], 2)}"
            )
            cells.append(
                f"<td style=\"background:{bg};color:{fg}\" title=\"{html.escape(title_text)}\">"
                f"{html.escape(_pct(value, 0))}</td>"
            )
        body.append(f"<tr><th class=\"bucket\">{html.escape(_display_bucket(bucket))}</th>{''.join(cells)}</tr>")
    return f"""
    <section>
      <h2>{html.escape(title)}</h2>
      <p class="note">{html.escape(note)}</p>
      <div class="heatmap-wrap">
        <table class="heatmap">
          <thead><tr><th class="bucket">rank / N</th>{head}</tr></thead>
          <tbody>{''.join(body)}</tbody>
        </table>
      </div>
    </section>
    """


def _svg_text(x: float, y: float, text: str, cls: str = "", anchor: str = "middle") -> str:
    return f"<text x=\"{x:.1f}\" y=\"{y:.1f}\" text-anchor=\"{anchor}\" class=\"{cls}\">{html.escape(text)}</text>"


def _render_scatter(rows: list[dict[str, Any]], candidate_keys: set[tuple[str, str, int]]) -> str:
    width, height = 980, 420
    left, right, top, bottom = 72, 28, 24, 58
    plot_w, plot_h = width - left - right, height - top - bottom
    xs = [row["avg_turnover"] for row in rows if not math.isnan(row["avg_turnover"])]
    ys = [row["compound_after_10bps"] for row in rows if not math.isnan(row["compound_after_10bps"])]
    x_max = max(xs) * 1.05 if xs else 1
    y_min = min(0.0, min(ys) if ys else 0.0)
    y_max = max(ys) * 1.08 if ys else 1
    if y_max == y_min:
        y_max = y_min + 1

    def sx(value: float) -> float:
        return left + (value / x_max) * plot_w

    def sy(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    parts = [
        f"<svg viewBox=\"0 0 {width} {height}\" class=\"scatter\" role=\"img\" aria-label=\"收益换手散点图\">",
        f"<rect x=\"0\" y=\"0\" width=\"{width}\" height=\"{height}\" fill=\"white\"/>",
    ]
    for idx in range(6):
        x_value = x_max * idx / 5
        x = sx(x_value)
        parts.append(f"<line x1=\"{x:.1f}\" y1=\"{top}\" x2=\"{x:.1f}\" y2=\"{top + plot_h}\" class=\"grid\"/>")
        parts.append(_svg_text(x, height - 24, _pct(x_value, 0), "axis"))
    for idx in range(6):
        y_value = y_min + (y_max - y_min) * idx / 5
        y = sy(y_value)
        parts.append(f"<line x1=\"{left}\" y1=\"{y:.1f}\" x2=\"{left + plot_w}\" y2=\"{y:.1f}\" class=\"grid\"/>")
        parts.append(_svg_text(left - 10, y + 4, _pct(y_value, 0), "axis", "end"))
    parts.append(f"<line x1=\"{left}\" y1=\"{top + plot_h}\" x2=\"{left + plot_w}\" y2=\"{top + plot_h}\" class=\"axis-line\"/>")
    parts.append(f"<line x1=\"{left}\" y1=\"{top}\" x2=\"{left}\" y2=\"{top + plot_h}\" class=\"axis-line\"/>")
    parts.append(_svg_text(left + plot_w / 2, height - 4, "平均换手", "label"))
    parts.append(_svg_text(14, top + plot_h / 2, "10bp后复利收益", "label vertical"))

    for row in rows:
        key = (row["family"], row["bucket"], row["window_days"])
        color = "#2563eb" if row["family"] == "topn" else "#16a34a"
        radius = 6 if key in candidate_keys else 3
        opacity = 0.9 if key in candidate_keys else 0.36
        x = sx(row["avg_turnover"])
        y = sy(row["compound_after_10bps"])
        title = (
            f"{_display_bucket(row['bucket'])} / {row['window_days']}日\\n"
            f"收益: {_pct(row['compound_after_10bps'], 2)}\\n"
            f"换手: {_pct(row['avg_turnover'], 2)}"
        )
        parts.append(
            f"<circle cx=\"{x:.1f}\" cy=\"{y:.1f}\" r=\"{radius}\" fill=\"{color}\" "
            f"opacity=\"{opacity}\"><title>{html.escape(title)}</title></circle>"
        )
        if key in candidate_keys:
            parts.append(_svg_text(x + 8, y - 8, f"{_display_bucket(row['bucket'])}/{row['window_days']}", "point-label", "start"))
    parts.append("</svg>")
    return f"""
    <section>
      <h2>收益-换手散点</h2>
      <p class="note">越靠上收益越高，越靠左换手越低；绿色为 rank 区间，蓝色为 TopN 前缀池。</p>
      <div class="chart-card">{''.join(parts)}</div>
    </section>
    """


def _render_monthly_chart(period_rows: list[dict[str, Any]], candidates: list[tuple[str, str, int, str]]) -> str:
    months = sorted({row["period"] for row in period_rows})
    series: list[tuple[str, str, list[float]]] = []
    colors = ("#166534", "#c2410c", "#7c3aed", "#2563eb")
    for idx, (family, bucket, window, label) in enumerate(candidates):
        values_by_month = {
            row["period"]: row["compound_return"]
            for row in period_rows
            if row["family"] == family and row["bucket"] == bucket and row["window_days"] == window
        }
        if values_by_month:
            series.append((label, colors[idx % len(colors)], [values_by_month.get(month, math.nan) for month in months]))
    if not months or not series:
        return ""

    width, height = 980, 390
    left, right, top, bottom = 70, 28, 24, 76
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [value for _, _, row_values in series for value in row_values if not math.isnan(value)]
    y_min = min(0.0, min(values))
    y_max = max(values)
    if y_max == y_min:
        y_max = y_min + 1

    def sx(index: int) -> float:
        if len(months) == 1:
            return left + plot_w / 2
        return left + index / (len(months) - 1) * plot_w

    def sy(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    parts = [
        f"<svg viewBox=\"0 0 {width} {height}\" class=\"monthly\" role=\"img\" aria-label=\"月度收益曲线\">",
        f"<rect x=\"0\" y=\"0\" width=\"{width}\" height=\"{height}\" fill=\"white\"/>",
    ]
    for idx in range(6):
        y_value = y_min + (y_max - y_min) * idx / 5
        y = sy(y_value)
        parts.append(f"<line x1=\"{left}\" y1=\"{y:.1f}\" x2=\"{left + plot_w}\" y2=\"{y:.1f}\" class=\"grid\"/>")
        parts.append(_svg_text(left - 10, y + 4, _pct(y_value, 0), "axis", "end"))
    zero_y = sy(0.0)
    parts.append(f"<line x1=\"{left}\" y1=\"{zero_y:.1f}\" x2=\"{left + plot_w}\" y2=\"{zero_y:.1f}\" class=\"zero-line\"/>")
    for idx, month in enumerate(months):
        x = sx(idx)
        parts.append(_svg_text(x, height - 42, month, "axis month"))

    for label, color, values_for_label in series:
        points = [(sx(idx), sy(value), value) for idx, value in enumerate(values_for_label) if not math.isnan(value)]
        polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        parts.append(f"<polyline points=\"{polyline}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2.4\"/>")
        for idx, (x, y, value) in enumerate(points):
            parts.append(
                f"<circle cx=\"{x:.1f}\" cy=\"{y:.1f}\" r=\"4\" fill=\"{color}\">"
                f"<title>{html.escape(label)} {months[idx]}: {_pct(value, 2)}</title></circle>"
            )
    legend_x = left
    for label, color, _ in series:
        parts.append(f"<rect x=\"{legend_x}\" y=\"{height - 22}\" width=\"12\" height=\"12\" fill=\"{color}\"/>")
        parts.append(_svg_text(legend_x + 18, height - 12, label, "legend", "start"))
        legend_x += min(245, 18 + len(label) * 8)
    parts.append("</svg>")
    return f"""
    <section>
      <h2>候选组合月度稳定性</h2>
      <p class="note">月度图使用 period.csv 的原始月度复利收益，未扣换手成本；主排序仍以 summary.csv 的 10bp 后复利收益为准。</p>
      <div class="chart-card">{''.join(parts)}</div>
    </section>
    """


def _render_table(headers: list[str], rows: Iterable[list[str]], class_name: str = "data-table") -> str:
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table class=\"{class_name}\"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _metric_row(label: str, row: dict[str, Any]) -> list[str]:
    return [
        html.escape(label),
        str(row["window_days"]),
        html.escape(_pct(row["compound_after_10bps"], 2)),
        html.escape(_pct(row["compound_return"], 2)),
        html.escape(_pct(row["avg_turnover"], 2)),
        html.escape(_pct(row["win_rate"], 2)),
        html.escape(_pct(row["max_drawdown_after_10bps"], 2)),
    ]


def _best_by_bucket(rows: list[dict[str, Any]], bucket_order: list[str]) -> list[list[str]]:
    result: list[list[str]] = []
    for bucket in bucket_order:
        bucket_rows = [row for row in rows if row["bucket"] == bucket]
        if not bucket_rows:
            continue
        best = max(bucket_rows, key=lambda row: row["compound_after_10bps"])
        result.append(_metric_row(_display_bucket(bucket), best))
    return result


def _render_report(summary_path: Path, period_path: Path, output_path: Path, title: str) -> None:
    rows = _read_summary(summary_path)
    monthly_rows = _read_monthly_periods(period_path)
    candidate_lookup = {
        (row["family"], row["bucket"], row["window_days"]): row
        for row in rows
    }
    candidates = [candidate for candidate in DEFAULT_CANDIDATES if candidate[:3] in candidate_lookup]
    candidate_keys = {candidate[:3] for candidate in candidates}
    values = [row["compound_after_10bps"] for row in rows if not math.isnan(row["compound_after_10bps"])]
    low = min(0.0, min(values))
    high = max(values)

    rank_deciles = ["rank1_10", "rank11_20", "rank21_30", "rank31_40", "rank41_50", "rank51_60", "rank61_70", "rank71_80", "rank81_90", "rank91_100"]
    rank_focused = ["rank1_20", "rank21_40", "rank41_60", "rank61_80", "rank81_100", "rank51_55", "rank56_60", "rank51_60", "rank51_80"]
    topn_order = ["top5", "top10", "top20", "top35", "top50", "top100", "all"]
    rank_rows = [row for row in rows if row["family"] == "rank_bucket"]
    topn_rows = [row for row in rows if row["family"] == "topn"]

    top_rows = sorted(rows, key=lambda row: row["compound_after_10bps"], reverse=True)[:15]
    low_turnover_rows = sorted(
        [row for row in rows if row["avg_turnover"] <= 0.30],
        key=lambda row: row["compound_after_10bps"],
        reverse=True,
    )[:12]

    candidate_table_rows = [
        _metric_row(label, candidate_lookup[(family, bucket, window)])
        for family, bucket, window, label in candidates
    ]
    top_table_rows = [
        _metric_row(f"{_display_bucket(row['bucket'])} / {row['window_days']}日", row)
        for row in top_rows
    ]
    low_turnover_table_rows = [
        _metric_row(f"{_display_bucket(row['bucket'])} / {row['window_days']}日", row)
        for row in low_turnover_rows
    ]
    headers = ["组合", "日数", "10bp后收益", "原始收益", "平均换手", "胜率", "10bp后最大回撤"]

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    best_row = max(rows, key=lambda row: row["compound_after_10bps"])
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #102033;
      --muted: #64748b;
      --line: #d8dee8;
      --panel: #ffffff;
      --page: #f4f7fb;
      --accent: #167953;
    }}
    body {{
      margin: 0;
      background: var(--page);
      color: var(--ink);
      font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    }}
    main {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 8px;
      font-size: 19px;
    }}
    section {{
      margin-top: 22px;
      padding: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .meta, .note {{
      color: var(--muted);
      margin: 0 0 12px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .metric {{
      background: #eef6f2;
      border: 1px solid #c8ded4;
      border-radius: 8px;
      padding: 12px;
    }}
    .metric b {{
      display: block;
      font-size: 20px;
      margin-bottom: 2px;
    }}
    .metric span {{
      color: #526175;
    }}
    .heatmap-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
    }}
    .heatmap {{
      min-width: 1520px;
      table-layout: fixed;
      font-size: 12px;
    }}
    th, td {{
      border-bottom: 1px solid #e5eaf1;
      border-right: 1px solid #edf1f6;
      padding: 7px 8px;
      text-align: right;
      white-space: nowrap;
    }}
    th {{
      background: #f8fafc;
      color: #475569;
      font-weight: 650;
    }}
    .bucket {{
      position: sticky;
      left: 0;
      z-index: 1;
      text-align: left;
      min-width: 92px;
    }}
    td.empty {{
      background: #f8fafc;
    }}
    .data-table th, .data-table td {{
      text-align: right;
    }}
    .data-table th:first-child, .data-table td:first-child {{
      text-align: left;
    }}
    .chart-card {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    svg {{
      display: block;
      min-width: 980px;
      width: 100%;
      height: auto;
    }}
    .grid {{
      stroke: #e2e8f0;
      stroke-width: 1;
    }}
    .axis-line, .zero-line {{
      stroke: #94a3b8;
      stroke-width: 1.2;
    }}
    .axis, .legend {{
      fill: #64748b;
      font-size: 12px;
    }}
    .label {{
      fill: #334155;
      font-size: 13px;
      font-weight: 650;
    }}
    .vertical {{
      writing-mode: tb;
      glyph-orientation-vertical: 0;
    }}
    .point-label {{
      fill: #0f172a;
      font-size: 12px;
      font-weight: 650;
    }}
    @media (max-width: 760px) {{
      main {{ padding: 18px 12px 32px; }}
      .summary {{ grid-template-columns: 1fr; }}
      section {{ padding: 14px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p class="meta">生成时间: {html.escape(generated_at)} | summary: {html.escape(str(summary_path))} | period: {html.escape(str(period_path))}</p>
    <div class="summary">
      <div class="metric"><b>{len(rows)}</b><span>参数组合</span></div>
      <div class="metric"><b>{_display_bucket(best_row['bucket'])} / {best_row['window_days']}日</b><span>10bp后收益最高: {_pct(best_row['compound_after_10bps'], 2)}</span></div>
      <div class="metric"><b>1-30日</b><span>推荐池日数横向对比</span></div>
      <div class="metric"><b>10bp</b><span>主图按单边换手成本后收益着色</span></div>
    </div>

    <section>
      <h2>候选组合</h2>
      <p class="note">这些组合来自当前诊断结论，用来在热力图和散点图里做定位。</p>
      {_render_table(headers, candidate_table_rows)}
    </section>

    {_render_heatmap("rank 十档热力图", "横轴是推荐池日数，纵轴是 rank 区间；颜色越深，10bp 后复利收益越高。", rank_rows, rank_deciles, low, high)}
    {_render_heatmap("重点 rank 区间热力图", "用于观察合并桶和 50-80/21-40 等区域是否是连续有效，而不是单点偶然。", rank_rows, rank_focused, low, high)}
    {_render_heatmap("TopN 前缀池热力图", "对比 Top5/Top10/Top20/Top50 等前缀池在不同推荐池日数下的收益变化。", topn_rows, topn_order, low, high)}

    {_render_scatter(rows, candidate_keys)}
    {_render_monthly_chart(monthly_rows, candidates)}

    <section>
      <h2>每个 rank 桶的最佳日数</h2>
      <p class="note">用于快速看同一 rank 桶内部，推荐池日数从短到长时哪个窗口最强。</p>
      {_render_table(headers, _best_by_bucket(rank_rows, rank_deciles + rank_focused))}
    </section>

    <section>
      <h2>全市场参数 Top 15</h2>
      <p class="note">按 10bp 后复利收益排序。高排名不等于默认推荐，还需要结合换手和回撤。</p>
      {_render_table(headers, top_table_rows)}
    </section>

    <section>
      <h2>低换手候选</h2>
      <p class="note">筛选平均换手不超过 30% 的组合，再按 10bp 后复利收益排序。</p>
      {_render_table(headers, low_turnover_table_rows)}
    </section>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a static HTML report for A-share pool rotation backtest grids.")
    parser.add_argument("--summary", required=True, help="Path to pool-rotation summary CSV.")
    parser.add_argument("--period", required=True, help="Path to pool-rotation period CSV.")
    parser.add_argument("--output", required=True, help="Output HTML path.")
    parser.add_argument("--title", default="A股推荐池轮动回测图表报告", help="Report title.")
    args = parser.parse_args()

    _render_report(
        summary_path=Path(args.summary),
        period_path=Path(args.period),
        output_path=Path(args.output),
        title=args.title,
    )
    print(Path(args.output))


if __name__ == "__main__":
    main()
