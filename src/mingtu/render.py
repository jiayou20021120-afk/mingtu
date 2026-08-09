#!/usr/bin/env python3
"""Render chart.json + lifeline.json into a single self-contained HTML scroll.

The whole point is that a life arc is a shape, not a list. Everything is inline
SVG and inline CSS; the file opens offline and prints cleanly.
"""
import argparse
import json
from html import escape

DIMS = ["事业", "财富", "婚恋", "健康", "学业", "人际"]
DIM_COLOR = {"事业": "#2f5d7c", "财富": "#8a6a2f", "婚恋": "#96504a",
             "健康": "#4a7a5c", "学业": "#5a4f7c", "人际": "#7c5a3f"}

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#faf8f4;color:#232025;
 font:16px/1.75 "Songti SC","Source Han Serif SC",Georgia,serif;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:56px 28px 96px}
h1{font-size:34px;letter-spacing:.06em;margin:0 0 6px;font-weight:600}
h2{font-size:15px;letter-spacing:.22em;font-weight:600;color:#8a7f6d;
 text-transform:none;margin:56px 0 18px;padding-bottom:9px;
 border-bottom:1px solid #e0d9cc}
.sub{color:#7d7364;font-size:14px;letter-spacing:.05em;margin-bottom:34px}
.pillars{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}
.pil{background:#fff;border:1px solid #e6dfd2;border-radius:3px;padding:16px 12px;
 text-align:center}
.pil .lab{font-size:11px;letter-spacing:.2em;color:#a1968a}
.pil .gz{font-size:31px;letter-spacing:.1em;margin:7px 0 4px}
.pil .ss{font-size:12px;color:#6f6558}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:11px}
.kv div{background:#fff;border:1px solid #e6dfd2;border-radius:3px;padding:11px 13px;
 font-size:13px}
.kv b{display:block;font-size:11px;letter-spacing:.16em;color:#a1968a;
 font-weight:600;margin-bottom:4px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{padding:9px 10px;border-bottom:1px solid #eae3d7;text-align:left}
th{font-size:11px;letter-spacing:.14em;color:#a1968a;font-weight:600}
tr.hot td{background:#fdf6ee}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:2px;
 background:#f0e9dc;color:#6f6558;margin:1px 3px 1px 0;letter-spacing:.04em}
.tag.maj{background:#efdcd6;color:#8c4436}
.conf-高{color:#4a7a5c}.conf-低{color:#96504a}.conf-分歧{color:#8a6a2f}
.conf-中{color:#7d7364}
.note{background:#fff;border-left:2px solid #c9bda8;padding:13px 17px;
 font-size:13.5px;color:#5e5548;margin:14px 0}
.legend{font-size:12px;color:#7d7364;margin:9px 0 0}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;
 margin:0 5px 0 14px;vertical-align:-1px}
footer{margin-top:64px;padding-top:20px;border-top:1px solid #e0d9cc;
 font-size:12px;color:#9b9184;line-height:1.9}
@media(prefers-color-scheme:dark){
 body{background:#17161a;color:#e6e1d8}
 .pil,.kv div,.note{background:#1f1e23;border-color:#333039}
 h2{color:#9b917f;border-color:#333039}
 th,td{border-color:#2b2930}tr.hot td{background:#241f1c}
 .tag{background:#2a2730;color:#b3a996}.tag.maj{background:#3d2a26;color:#d99b8a}
 .note{border-left-color:#4a4438}footer{border-color:#333039}}
"""


def arc_svg(cycles):
    """Ten luck cycles as a proportional band. Height = rank within own life."""
    W, H, pad = 1020, 190, 30
    scored = [c for c in cycles if c["ganzhi"] != "(起运前)"]
    n = len(scored)
    bw = (W - 2 * pad) / n
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" '
             f'style="display:block;margin:16px 0">']
    parts.append(f'<line x1="{pad}" y1="{H-34}" x2="{W-pad}" y2="{H-34}" '
                 f'stroke="#d8cfbe" stroke-width="1"/>')
    for i, c in enumerate(scored):
        x = pad + i * bw
        h = 14 + c.get("relative", 0.5) * 108
        y = H - 34 - h
        col = DIM_COLOR.get(c["dominant_dimension"], "#6f6558")
        op = 0.30 + 0.55 * c.get("relative", 0.5)
        parts.append(f'<rect x="{x+3:.1f}" y="{y:.1f}" width="{bw-6:.1f}" '
                     f'height="{h:.1f}" fill="{col}" opacity="{op:.2f}" rx="2"/>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{y-7:.1f}" text-anchor="middle" '
                     f'font-size="12" fill="#6f6558">{escape(c["ganzhi"])}</text>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{H-19:.1f}" text-anchor="middle" '
                     f'font-size="11" fill="#a1968a">'
                     f'{c["age_range"][0]}–{c["age_range"][1]}岁</text>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{H-6:.1f}" text-anchor="middle" '
                     f'font-size="10" fill="#b5aa9b">'
                     f'#{c.get("rank","-")} {escape(c["dominant_dimension"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def year_svg(years, dims_shown):
    """Six-dimension traces across the whole life, plus turning-point ticks."""
    W, H = 1020, 320
    padl, padr, padt, padb = 40, 16, 18, 40
    ys = [r for r in years if r["age"] <= 85]
    n = len(ys)
    lo = min(min(r["dims"][d] for d in DIMS) for r in ys)
    hi = max(max(r["dims"][d] for d in DIMS) for r in ys)
    span = (hi - lo) or 1.0

    def px(i):
        return padl + i * (W - padl - padr) / max(1, n - 1)

    def py(v):
        return padt + (1 - (v - lo) / span) * (H - padt - padb)

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" '
             f'style="display:block;margin:16px 0">']
    zero = py(0)
    parts.append(f'<line x1="{padl}" y1="{zero:.1f}" x2="{W-padr}" y2="{zero:.1f}" '
                 f'stroke="#d8cfbe" stroke-dasharray="3 3"/>')
    for r in ys:
        if r["age"] % 10 == 0:
            x = px(r["age"])
            parts.append(f'<line x1="{x:.1f}" y1="{padt}" x2="{x:.1f}" '
                         f'y2="{H-padb}" stroke="#efe8db"/>')
            parts.append(f'<text x="{x:.1f}" y="{H-padb+16}" text-anchor="middle" '
                         f'font-size="10.5" fill="#a1968a">{r["age"]}岁</text>')
            parts.append(f'<text x="{x:.1f}" y="{H-padb+29}" text-anchor="middle" '
                         f'font-size="9.5" fill="#c0b6a6">{r["year"]}</text>')
    for d in dims_shown:
        pts = " ".join(f"{px(r['age']):.1f},{py(r['dims'][d]):.1f}" for r in ys)
        parts.append(f'<polyline points="{pts}" fill="none" '
                     f'stroke="{DIM_COLOR[d]}" stroke-width="1.6" opacity="0.85"/>')
    for r in ys:
        majors = [e for e in r["events"] if e["level"] == "major"]
        if len(majors) >= 2:
            x = px(r["age"])
            parts.append(f'<circle cx="{x:.1f}" cy="{padt-4}" r="3" '
                         f'fill="#8c4436" opacity="0.8"/>')
    parts.append("</svg>")
    return "".join(parts)


def build_html(chart, life, focus_from=None, focus_to=None):
    birth = life["meta"]["birth_year"]
    focus_from = focus_from or birth + 18
    focus_to = focus_to or focus_from + 24
    m, b, z = chart["meta"], chart["bazi"], chart["ziwei"]
    lm, ov = life["meta"], life["overview"]

    pil = "".join(
        f'<div class="pil"><div class="lab">{p["pos"]}柱</div>'
        f'<div class="gz">{p["ganzhi"]}</div>'
        f'<div class="ss">{p["shishen_gan"]} · {p["nayin"]}</div>'
        f'<div class="ss" style="color:#a1968a">{p["dishi"]}</div></div>'
        for p in b["pillars"])

    kv = [
        ("日主", f'{b["day_master"]["gan"]}（{b["day_master"]["yinyang"]}'
                 f'{b["day_master"]["wuxing"]}）· {b["strength"]["label"]}'),
        ("格局", f'{b["geju"]["name"]} · {b["geju"]["status"]}'),
        ("用神", f'{"、".join(b["yongshen"]["favor"])}'
                 f'（{b["yongshen"]["method"]}）'),
        ("忌神", "、".join(b["yongshen"]["avoid"])),
        ("紫微命宫", f'{z["soul_palace_zhi"]}宫 · {z["soul_star"]}'),
        ("五行局", f'{z["wuxingju"]} · 身主{z["body_star"]}'),
        ("生年四化", " ".join(f'{k}→{v["star"]}({v["palace"]})'
                              for k, v in z["birth_mutagen"].items())),
        ("时辰", f'{m["shichen_effective"]}时'
                 + ("（真太阳时校正后）" if m["true_solar_time_applied"] else "（未校正）")
                 + ("　⚠ 跨时辰边界" if m["shichen_boundary_flip"] else "")),
    ]
    kvh = "".join(f"<div><b>{escape(k)}</b>{escape(str(v))}</div>" for k, v in kv)

    cyc_rows = []
    for c in life["cycles"]:
        if c["ganzhi"] == "(起运前)":
            continue
        tags = "".join(f'<span class="tag maj">{escape(e["tag"])}</span>'
                       for e in c["major_events"][:3])
        cyc_rows.append(
            f'<tr><td><b>{escape(c["ganzhi"])}</b> '
            f'<span style="color:#a1968a">{escape(c["shishen"] or "")}</span></td>'
            f'<td>{c["age_range"][0]}–{c["age_range"][1]}岁</td>'
            f'<td>{c["year_range"][0]}–{c["year_range"][1]}</td>'
            f'<td>#{c.get("rank","-")}/{c.get("rank_of","-")}</td>'
            f'<td>{escape(c["dominant_dimension"])}</td>'
            f'<td>{escape(c["weakest_dimension"])}</td>'
            f'<td>{tags}</td></tr>')

    focus = [r for r in life["years"] if focus_from <= r["year"] <= focus_to]
    yr_rows = []
    for r in focus:
        majors = [e for e in r["events"] if e["level"] == "major"]
        tags = "".join(
            f'<span class="tag{" maj" if e["level"]=="major" else ""}">'
            f'{escape(e["tag"])}</span>' for e in r["events"][:4])
        top = max(r["dims"], key=r["dims"].get)
        bot = min(r["dims"], key=r["dims"].get)
        yr_rows.append(
            f'<tr class="{"hot" if majors else ""}">'
            f'<td><b>{r["year"]}</b> <span style="color:#a1968a">'
            f'{escape(r["ganzhi"])}</span></td>'
            f'<td>{r["age"]}岁</td>'
            f'<td>{escape(r["dayun"]["ganzhi"] or "—")}</td>'
            f'<td>{escape(top)} {r["dims"][top]:+.1f}</td>'
            f'<td>{escape(bot)} {r["dims"][bot]:+.1f}</td>'
            f'<td class="conf-{r["confidence"]}">{r["confidence"]}</td>'
            f'<td>{tags}</td></tr>')

    tp_rows = []
    for t in ov["turning_points"]:
        tags = "".join(f'<span class="tag maj">{escape(x)}</span>' for x in t["tags"])
        tp_rows.append(f'<tr><td><b>{t["year"]}</b></td><td>{t["age"]}岁</td>'
                       f'<td>{tags}</td><td>权重 {t["weight"]}</td></tr>')
    tps = "".join(tp_rows)

    legend = "".join(f'<i style="background:{DIM_COLOR[d]}"></i>{d}' for d in DIMS)
    agree = sum(1 for r in life["years"] if r["confidence"] == "高")
    disagree = sum(1 for r in life["years"] if r["confidence"] in ("低", "分歧"))

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(m['name'])} · 命途</title><style>{CSS}</style></head><body><div class="wrap">
<h1>{escape(m['name'])}　命途</h1>
<div class="sub">{escape(m['clock_time'])}　{escape(m['gender'])}命
{escape(m.get('city') or '未填出生地')}　·　{escape(m['lunar'])}</div>

<h2>本命</h2>
<div class="pillars">{pil}</div>
<div class="kv">{kvh}</div>
<div class="note">{escape(b['yongshen']['reason'])}</div>

<h2>十步大运</h2>
{arc_svg(life['cycles'])}
<div class="legend">柱高＝该步在本人十步大运中的相对位次，颜色＝该步最强的维度{legend}</div>
<table><tr><th>大运</th><th>年龄</th><th>年份</th><th>位次</th>
<th>最强</th><th>最弱</th><th>结构事件</th></tr>{''.join(cyc_rows)}</table>

<h2>六维全程曲线</h2>
{year_svg(life['years'], DIMS)}
<div class="legend">上缘红点＝该年叠加两项以上结构性事件{legend}</div>

<h2>关键转折</h2>
<table><tr><th>年份</th><th>年龄</th><th>信号</th><th></th></tr>{tps}</table>

<h2>逐年细目 · {focus_from}–{focus_to}</h2>
<table><tr><th>流年</th><th>年龄</th><th>大运</th><th>最强维度</th>
<th>最弱维度</th><th>双盘一致度</th><th>事件</th></tr>{''.join(yr_rows)}</table>

<footer>
八字与紫微斗数由两套独立算法分别推演，逐年交叉对账。全生命周期
{len(life['years'])} 年中，两套体系强一致 {agree} 年，分歧或相反 {disagree} 年——
分歧年份的结论请当作待定，不要当作结论。<br>
维度分区间 −5…+5，衡量的是结构性倾向，不是概率，更不是事实。<br>
本页仅供传统文化研究与自我参照，不构成医疗、投资、婚姻、法律等任何决策依据。
</footer></div></body></html>"""
