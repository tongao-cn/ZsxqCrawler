#!/usr/bin/env python3
import argparse
import csv
import json
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Tuple
import os

def read_csv(path: str) -> Tuple[List[str], Dict[str, Dict[str, int]]]:
    daily: Dict[str, Dict[str, int]] = {}
    if not os.path.exists(path):
        return [], {}
    with open(path, "r", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) < 3:
                continue
            day = row[0].strip()
            company = row[1].strip()
            try:
                cnt = int(row[2].strip())
            except Exception:
                cnt = 0
            if day not in daily:
                daily[day] = {}
            daily[day][company] = daily[day].get(company, 0) + cnt
    dates = sorted(daily.keys())
    ordered: Dict[str, Dict[str, int]] = {}
    for d in dates:
        ordered[d] = daily.get(d, {})
    return dates, ordered

def pick_colors(n: int) -> List[str]:
    colors = []
    for _ in range(n):
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        colors.append(f"rgba({r},{g},{b},0.8)")
    return colors

def build_html(dates: List[str], daily: Dict[str, Dict[str, int]], top: int) -> bytes:
    payload = {"dates": dates, "daily": daily, "top": top}
    html = f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>公司累计推荐次数</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 20px; }}
      #container {{ max-width: 1200px; margin: 0 auto; }}
      #meta {{ margin-bottom: 12px; color: #555; }}
      canvas {{ width: 100% !important; height: 520px !important; }}
      #controls {{ display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }}
      select {{ padding: 6px 8px; }}
      #rankings {{ margin-top: 20px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
      .ranking-col {{ border: 1px solid #d9d9d9; border-radius: 8px; padding: 10px; background: #fafafa; }}
      .ranking-col h3 {{ margin: 0 0 8px; font-size: 15px; }}
      .ranking-list {{ list-style: none; margin: 0; padding: 0; }}
      .ranking-list li {{ display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; gap: 8px; font-size: 13px; line-height: 1.5; padding: 2px 0; border-bottom: 1px dotted #ececec; }}
      .ranking-list li:last-child {{ border-bottom: 0; }}
      .rank-no {{ color: #666; }}
      .rank-company {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
      .rank-cnt {{ color: #111; font-variant-numeric: tabular-nums; }}
      .ranking-list .empty {{ display: block; color: #888; border-bottom: 0; }}
      @media (max-width: 980px) {{ #rankings {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
      @media (max-width: 640px) {{ #rankings {{ grid-template-columns: 1fr; }} }}
    </style>
  </head>
  <body>
    <div id="container">
      <h2>公司累计推荐次数折线图</h2>
      <div id="controls">
        <label>开始日期:
          <select id="start"></select>
        </label>
        <label>结束日期:
          <select id="end"></select>
        </label>
      </div>
      <div id="meta"></div>
      <canvas id="chart"></canvas>
      <div id="rankings">
        <div class="ranking-col">
          <h3>3日推荐池排序（Top35）</h3>
          <ol id="rank-3" class="ranking-list"></ol>
        </div>
        <div class="ranking-col">
          <h3>7日推荐池排序（Top35）</h3>
          <ol id="rank-7" class="ranking-list"></ol>
        </div>
        <div class="ranking-col">
          <h3>14日推荐池排序（Top35）</h3>
          <ol id="rank-14" class="ranking-list"></ol>
        </div>
        <div class="ranking-col">
          <h3>21日推荐池排序（Top35）</h3>
          <ol id="rank-21" class="ranking-list"></ol>
        </div>
      </div>
    </div>
    <script>
      const payload = {json.dumps(payload, ensure_ascii=False)};
      const dates = payload.dates;
      const daily = payload.daily;
      const topN = payload.top || 20;
      const rankTopN = 35;
      const rankWindows = [3, 7, 14, 21];
      const startSel = document.getElementById('start');
      const endSel = document.getElementById('end');
      const meta = document.getElementById('meta');
      const rankEls = {{
        3: document.getElementById('rank-3'),
        7: document.getElementById('rank-7'),
        14: document.getElementById('rank-14'),
        21: document.getElementById('rank-21')
      }};
      for (let i = 0; i < dates.length; i++) {{
        const d = dates[i];
        const opt1 = document.createElement('option'); opt1.value = i; opt1.textContent = d; startSel.appendChild(opt1);
        const opt2 = document.createElement('option'); opt2.value = i; opt2.textContent = d; endSel.appendChild(opt2);
      }}
      if (dates.length > 0) {{
        startSel.value = "0";
        endSel.value = String(dates.length - 1);
      }}
      function computeRangeData(startIdx, endIdx) {{
        if (dates.length === 0 || endIdx < startIdx) {{
          return {{ labels: [], datasets: [], companiesCount: 0 }};
        }}
        const labels = dates.slice(startIdx, endIdx + 1);
        const companySet = {{}};
        for (let i = startIdx; i <= endIdx; i++) {{
          const d = dates[i];
          const row = daily[d] || {{}};
          for (const c in row) companySet[c] = true;
        }}
        const companies = Object.keys(companySet);
        const datasets = [];
        const totals = [];
        for (const c of companies) {{
          let total = 0;
          const seq = [];
          for (let i = startIdx; i <= endIdx; i++) {{
            const d = dates[i];
            const v = (daily[d] && daily[d][c]) ? daily[d][c] : 0;
            total += v;
            seq.push(total);
          }}
          const last = seq.length ? seq[seq.length - 1] : 0;
          if (last > 0) {{
            totals.push([c, last, seq]);
          }}
        }}
        totals.sort((a,b) => b[1] - a[1]);
        const pick = totals.slice(0, topN);
        const colors = [];
        for (let k = 0; k < pick.length; k++) {{
          const r = Math.floor(Math.random()*256);
          const g = Math.floor(Math.random()*256);
          const b = Math.floor(Math.random()*256);
          colors.push(`rgba(${{r}},${{g}},${{b}},0.8)`);
        }}
        for (let i = 0; i < pick.length; i++) {{
          const c = pick[i][0];
          const seq = pick[i][2];
          datasets.push({{ label: c, data: seq, borderColor: colors[i], backgroundColor: colors[i], fill: false, tension: 0.2 }});
        }}
        return {{ labels, datasets, companiesCount: pick.length }};
      }}
      function escapeHtml(text) {{
        const map = {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }};
        return String(text).replace(/[&<>"']/g, (m) => map[m]);
      }}
      function computePoolRanking(startIdx, endIdx, days) {{
        if (dates.length === 0 || endIdx < 0) return [];
        const fromIdx = Math.max(startIdx, endIdx - days + 1);
        const totals = {{}};
        for (let i = fromIdx; i <= endIdx; i++) {{
          const d = dates[i];
          const row = daily[d] || {{}};
          for (const c in row) {{
            totals[c] = (totals[c] || 0) + row[c];
          }}
        }}
        return Object.entries(totals)
          .filter(([, v]) => v > 0)
          .sort((a, b) => b[1] - a[1])
          .slice(0, rankTopN);
      }}
      function renderPoolRanking(startIdx, endIdx) {{
        for (const days of rankWindows) {{
          const el = rankEls[days];
          if (!el) continue;
          const rows = computePoolRanking(startIdx, endIdx, days);
          if (rows.length === 0) {{
            el.innerHTML = '<li class="empty">暂无数据</li>';
            continue;
          }}
          el.innerHTML = rows.map((row, idx) =>
            `<li><span class="rank-no">${{idx + 1}}</span><span class="rank-company">${{escapeHtml(row[0])}}</span><span class="rank-cnt">${{row[1]}}</span></li>`
          ).join('');
        }}
      }}
      const ctx = document.getElementById('chart').getContext('2d');
      const initial = computeRangeData(Number(startSel.value), Number(endSel.value));
      const chart = new Chart(ctx, {{
        type: 'line',
        data: {{ labels: initial.labels, datasets: initial.datasets }},
        options: {{
          responsive: true,
          interaction: {{ mode: 'nearest', axis: 'x', intersect: false }},
          plugins: {{
            legend: {{ position: 'top' }},
            tooltip: {{
              callbacks: {{
                label: (context) => {{
                  const l = context.dataset.label || '';
                  const v = context.parsed.y;
                  return l + ': ' + v;
                }}
              }}
            }}
          }},
          scales: {{
            x: {{ title: {{ display: true, text: '日期' }} }},
            y: {{ title: {{ display: true, text: '累计推荐次数' }}, beginAtZero: true }}
          }}
        }}
      }});
      function refresh() {{
        if (dates.length === 0) {{
          chart.data.labels = [];
          chart.data.datasets = [];
          chart.update();
          renderPoolRanking(0, -1);
          meta.textContent = '暂无可用数据';
          return;
        }}
        let s = Number(startSel.value), e = Number(endSel.value);
        if (s > e) [s, e] = [e, s];
        const x = computeRangeData(s, e);
        chart.data.labels = x.labels;
        chart.data.datasets = x.datasets;
        chart.update();
        renderPoolRanking(s, e);
        meta.textContent = '公司数: ' + x.companiesCount + '，日期数: ' + x.labels.length;
      }}
      startSel.addEventListener('change', refresh);
      endSel.addEventListener('change', refresh);
      refresh();
    </script>
  </body>
</html>
"""
    return html.encode("utf-8")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index.html"):
            content = self.server._html
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not Found")

def serve(csv_path: str, port: int, top: int):
    dates, daily = read_csv(csv_path)
    html = build_html(dates, daily, top)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server._html = html
    print(f"Serving chart on http://localhost:{port}/ using {csv_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=str, default="output/company_mentions_last_month.csv")
    p.add_argument("--port", type=int, default=8350)
    p.add_argument("--top", type=int, default=50)
    args = p.parse_args()
    serve(args.csv, args.port, args.top)

if __name__ == "__main__":
    main()

