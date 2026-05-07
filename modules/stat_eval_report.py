"""
从 *_statistical_eval.xlsx 生成单页 HTML 可视化报告（内嵌 SVG，无需 matplotlib）。
"""
from __future__ import annotations

import html
import os
from datetime import datetime

import pandas as pd

CLUSTER_COLORS = ("#2563eb", "#16a34a", "#ca8a04", "#dc2626", "#7c3aed", "#0891b2")


def _to_float(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_bool(val):
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("true", "1", "yes", "是")


def _svg_bar_summary(ok: int, bad: int, w: int = 520, h: int = 160) -> str:
    total = max(1, ok + bad)
    bw = (w - 80) // 2
    h1 = int((h - 60) * ok / total)
    h2 = int((h - 60) * bad / total)
    y1 = 40 + (h - 60 - h1)
    y2 = 40 + (h - 60 - h2)
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" role="img" aria-label="结果概览">
  <text x="10" y="22" font-size="14" font-weight="600" fill="#1e293b">牌名级结果</text>
  <rect x="40" y="{y1}" width="{bw}" height="{h1}" fill="#22c55e" rx="4"/>
  <rect x="{40 + bw + 40}" y="{y2}" width="{bw}" height="{h2}" fill="#f87171" rx="4"/>
  <text x="{40 + bw // 2}" y="{h - 8}" text-anchor="middle" font-size="12" fill="#334155">统计可用</text>
  <text x="{40 + bw + 40 + bw // 2}" y="{h - 8}" text-anchor="middle" font-size="12" fill="#334155">需人工/打开链接</text>
  <text x="{40 + bw // 2}" y="{y1 - 6}" text-anchor="middle" font-size="13" font-weight="600" fill="#14532d">{ok}</text>
  <text x="{40 + bw + 40 + bw // 2}" y="{y2 - 6}" text-anchor="middle" font-size="13" font-weight="600" fill="#7f1d1d">{bad}</text>
</svg>
"""


def _svg_card_clusters(
    card_name: str,
    cdf: pd.DataFrame,
    w: int = 720,
    row_h: int = 36,
    margin_l: int = 120,
    margin_r: int = 24,
) -> str:
    """每个簇一条横线：最低价—最高价，中位价圆点；选中簇加粗边框。"""
    if cdf.empty:
        return f'<p class="muted">无簇数据</p>'

    prices = []
    for _, r in cdf.iterrows():
        for k in ("cluster_min_price", "cluster_max_price", "cluster_median_price"):
            v = _to_float(r.get(k))
            if v is not None:
                prices.append(v)
    if not prices:
        return f'<p class="muted">无价格数据</p>'

    p_lo, p_hi = min(prices), max(prices)
    if p_hi <= p_lo:
        p_hi = p_lo + 1.0

    def x_for(p: float) -> float:
        return margin_l + (p - p_lo) / (p_hi - p_lo) * (w - margin_l - margin_r)

    n = len(cdf)
    h = 28 + n * row_h + 32
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" class="cluster-svg">',
        f'<text x="8" y="18" font-size="12" fill="#64748b">{html.escape(card_name[:40])}</text>',
        f'<line x1="{margin_l}" y1="{h - 20}" x2="{w - margin_r}" y2="{h - 20}" stroke="#cbd5e1" stroke-width="1"/>',
        f'<text x="{margin_l}" y="{h - 4}" font-size="10" fill="#64748b">{p_lo:.2f}</text>',
        f'<text x="{w - margin_r}" y="{h - 4}" font-size="10" fill="#64748b" text-anchor="end">{p_hi:.2f}</text>',
    ]

    for i, (_, r) in enumerate(cdf.iterrows()):
        cid = int(float(r.get("cluster_id", i + 1)) or i + 1)
        color = CLUSTER_COLORS[(cid - 1) % len(CLUSTER_COLORS)]
        y = 32 + i * row_h
        mn = _to_float(r.get("cluster_min_price"))
        mx = _to_float(r.get("cluster_max_price"))
        md = _to_float(r.get("cluster_median_price"))
        if mn is None or mx is None:
            continue
        x1, x2 = x_for(mn), x_for(mx)
        selected = _to_bool(r.get("is_selected_lowest", False))
        credible = _to_bool(r.get("is_credible", False))
        stroke = "#0f172a" if selected else "#94a3b8"
        sw = 3 if selected else 1.5
        lines.append(
            f'<line x1="{x1:.1f}" y1="{y}" x2="{x2:.1f}" y2="{y}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>'
        )
        lines.append(
            f'<rect x="{x1 - 2:.1f}" y="{y - 6}" width="{max(4, x2 - x1):.1f}" height="12" fill="none" stroke="{stroke}" stroke-width="{sw}" rx="2"/>'
        )
        if md is not None:
            xd = x_for(md)
            lines.append(
                f'<circle cx="{xd:.1f}" cy="{y}" r="5" fill="white" stroke="{color}" stroke-width="2"/>'
            )
        cnt = r.get("cluster_listing_count", "")
        label = f"簇{cid} · {cnt}条"
        if selected:
            label += " ← 选用"
        elif not credible:
            label += "（未达标）"
        lines.append(
            f'<text x="8" y="{y + 4}" font-size="11" fill="#475569">{html.escape(str(label))}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def build_html_report(stat_eval_path: str) -> str:
    all_cards = pd.read_excel(stat_eval_path, sheet_name="all_cards", engine="openpyxl")
    clusters = pd.read_excel(stat_eval_path, sheet_name="clusters", engine="openpyxl")

    rs = all_cards.get("routing_suggestion", pd.Series(dtype=str)).astype(str)
    ok = int((rs == "statistical_candidate").sum())
    bad = int((rs == "open_url_fallback").sum())

    # 简化表列
    simple_cols = [
        "card_name",
        "routing_suggestion",
        "effective_min_cluster_size",
        "old_release_rule_hit",
        "valid_price_count",
        "cluster_count",
        "target_value",
        "secondary_reason",
    ]
    present = [c for c in simple_cols if c in all_cards.columns]
    simple_df = all_cards[present].copy()
    if "routing_suggestion" in simple_df.columns:
        simple_df["_sort"] = simple_df["routing_suggestion"].map(
            {"open_url_fallback": 0, "statistical_candidate": 1}
        ).fillna(2)
        simple_df = simple_df.sort_values("_sort").drop(columns=["_sort"])

    rows_html = []
    for _, row in simple_df.iterrows():
        cells = []
        for c in present:
            v = row.get(c, "")
            if pd.isna(v):
                v = ""
            cells.append(f"<td>{html.escape(str(v))}</td>")
        cls = "row-ok" if str(row.get("routing_suggestion", "")) == "statistical_candidate" else "row-bad"
        rows_html.append(f'<tr class="{cls}">{"".join(cells)}</tr>')

    # 按牌名分组簇
    card_sections = []
    ordered_names = (
        simple_df["card_name"].astype(str).tolist()
        if not simple_df.empty and "card_name" in simple_df.columns
        else all_cards["card_name"].astype(str).unique().tolist()
    )
    for name in ordered_names:
        cdf = clusters[clusters["card_name"].astype(str) == name].copy()
        if "cluster_id" in cdf.columns:
            cdf = cdf.sort_values("cluster_id")
        row = all_cards[all_cards["card_name"].astype(str) == name].iloc[0]
        status = str(row.get("routing_suggestion", ""))
        badge = '<span class="badge ok">统计可用</span>' if status == "statistical_candidate" else '<span class="badge bad">未通过</span>'
        tv = row.get("target_value", "")
        reason = row.get("secondary_reason", "")
        if pd.isna(tv):
            tv = ""
        if pd.isna(reason):
            reason = ""
        card_sections.append(
            f"""
<section class="card-block">
  <h3>{html.escape(name)} {badge}</h3>
  <p class="meta">回填价 target_value：<strong>{html.escape(str(tv))}</strong>
  &nbsp;|&nbsp; 失败说明：{html.escape(str(reason)) if reason else "—"}</p>
  {_svg_card_clusters(name, cdf)}
</section>
"""
        )

    title = os.path.basename(stat_eval_path)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>统计评估可视化 — {html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --card: #fff;
      --text: #0f172a;
      --muted: #64748b;
      --border: #e2e8f0;
    }}
    body {{
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
      max-width: 920px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    h1 {{ font-size: 1.35rem; margin-bottom: 0.25rem; }}
    .sub {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
    .explain {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 18px;
      margin-bottom: 24px;
    }}
    .explain h2 {{ font-size: 1.05rem; margin-top: 0; }}
    .explain ul {{ margin: 0.5rem 0 0 1.1rem; }}
    .explain code {{ background: #f1f5f9; padding: 0 4px; border-radius: 4px; font-size: 0.88em; }}
    .viz-wrap {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 24px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; background: var(--card); border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }}
    th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ background: #f1f5f9; font-weight: 600; }}
    tr.row-ok {{ background: #f0fdf4; }}
    tr.row-bad {{ background: #fef2f2; }}
    .card-block {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px 8px;
      margin-bottom: 18px;
    }}
    .card-block h3 {{ font-size: 1rem; margin: 0 0 6px 0; }}
    .meta {{ font-size: 0.85rem; color: var(--muted); margin: 0 0 10px 0; }}
    .badge {{ font-size: 0.75rem; padding: 2px 8px; border-radius: 999px; vertical-align: middle; }}
    .badge.ok {{ background: #dcfce7; color: #166534; }}
    .badge.bad {{ background: #fee2e2; color: #991b1b; }}
    .muted {{ color: var(--muted); }}
    .cluster-svg {{ display: block; max-width: 100%; height: auto; }}
    .mermaid {{ background: #fff; border: 1px dashed var(--border); border-radius: 8px; padding: 12px; text-align: center; }}
  </style>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "neutral" }});
  </script>
</head>
<body>
  <h1>牌名级「最低可信货盘」诊断报告</h1>
  <p class="sub">源文件：{html.escape(stat_eval_path)}<br/>生成时间：{generated}</p>

  <div class="explain">
    <h2>这张报告在说什么？</h2>
    <p>你在淘宝同一<strong>牌名</strong>下收集了很多商品链接，每条有一个<strong>一口价</strong>。这些价里往往混着「大路货」和「更贵的版本/错挂价」。本工具从<strong>最低价开始贪心生长</strong>，把相邻价格逐步纳入当前簇——只要与簇底价的<strong>绝对差 ≤ <code>abs_tolerance</code></strong> 或 <strong>倍率 ≤ <code>max_span_ratio</code></strong>（满足其一即可），就继续归入；否则开始新簇。</p>
    <p>算法先定位<strong>第一个</strong>（价格最低的）满足 <code>min_cluster_size</code> 的簇；然后判断其前方是否存在“前缀池”：<strong>先看量</strong>（前缀样本条数 ≥ <code>min_cluster_size</code>），再看与后续价带是否有<strong>断层</strong>（<code>prefix_pool_gap_abs</code> 或 <code>prefix_pool_gap_ratio</code>，满足其一）。前缀占比仅作诊断输出，不作门槛；亦不再要求全牌有效样本条数达到额外下限才尝试前缀池。</p>
    <p>若“量+断层”都通过，则直接采用前缀池回填（<code>routing_reason=prefix_pool_selected</code>）；若“量”通过但“断层”不足，可按 <code>block_if_prefix_mass_without_gap</code> 选择保守阻断（走 fallback）或回退到首个大簇。</p>
    <p><strong>最低可信货盘</strong>来自：单簇够大，或经前缀池存在判定通过的低价前缀池。</p>
    <p>若选中成功，牌名会标记为<strong>统计可用</strong>，并用该簇内价格按 <code>target_quantile</code>（例如 0.25，不加权）算出一个 <code>target_value</code> 供后续回填。右侧若还有更高价的货盘，通常表现为图上<strong>更靠右的另一条色带</strong>。</p>
    <p><strong>图例（每张牌名下方的条带图）</strong>：彩色粗线 = 该簇最低价到最高价；白心圆 = 中位价；<strong>黑框</strong> = 最终被选用的簇；「未达标」= 条数不满足成簇门槛，不会当选。</p>
    <p>注意：成簇门槛默认是 <code>min_cluster_size</code>（例如 4）；但如果某牌名下<strong>所有</strong>行的“发售时间”都可解析，且都早于 <code>old_release_cutoff_date</code>（默认 2009-10-01），则该牌名会启用更低门槛 <code>old_release_min_cluster_size</code>（默认 3）。简表中的 <code>effective_min_cluster_size</code> 会展示每个牌名实际使用的门槛。</p>
  </div>

  <div class="viz-wrap">
    <h2 style="margin-top:0;font-size:1.05rem;">总体比例</h2>
    {_svg_bar_summary(ok, bad)}
    <p class="muted" style="margin:8px 0 0;font-size:0.88rem;">绿色：统计可用（{ok} 个牌名）　红色：未通过、建议走打开链接等兜底（{bad} 个牌名）</p>
  </div>

  <div class="explain">
    <h2>流程简图（与 Excel 无关，帮助记逻辑）</h2>
    <pre class="mermaid">
flowchart LR
  A[一口价列表] --> B[按价格升序排列]
  B --> C[从最低价贪心生长]
  C --> D{{绝对差或倍率在容忍内}}
  D -->|是| E[纳入当前簇]
  D -->|否| F[开始新簇]
  E --> D
  F --> D
  D -->|遍历完| G[定位首个够大簇]
  G --> H{{前缀池量判据通过}}
  H -->|否| I[用首个大簇]
  H -->|是| J{{断层判据通过}}
  J -->|是| K[用前缀池]
  J -->|否| L[阻断或回退首个大簇]
  I --> M[按P25得到回填价]
  K --> M
  L --> M
    </pre>
  </div>

  <h2 style="font-size:1.05rem;">牌名简表（从宽表里抽的几列）</h2>
  <table>
    <thead><tr>{"".join(f"<th>{html.escape(c)}</th>" for c in present)}</tr></thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>

  <h2 style="font-size:1.05rem;margin-top:28px;">按牌名：货盘条带图</h2>
  {"".join(card_sections)}

  <p class="muted" style="margin-top:32px;font-size:0.85rem;">提示：流程图依赖 CDN 加载 Mermaid；若离线打开不显示，可忽略，不影响上方数据与 SVG 图。</p>
</body>
</html>
"""
    return doc


def write_report(stat_eval_path: str, output_path: str | None = None) -> str:
    if output_path is None:
        base, _ = os.path.splitext(stat_eval_path)
        output_path = f"{base}_report.html"
    html_str = build_html_report(stat_eval_path)
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_str)
    return output_path
