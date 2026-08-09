"""Recover an unknown birth hour by testing all twelve against known life events.

Most tools give up when the hour is missing, or silently guess 子时 — which
corrupts the day pillar, the day master, the pattern and every downstream year.
This does what a practitioner actually does: build all twelve charts, score each
against events the person can confirm already happened, and report the ranking
with its margin. A narrow margin means the hour is NOT recovered, and the script
says so rather than picking a winner.
"""
import json
from pathlib import Path
from types import SimpleNamespace

from .chart import build as build_chart
from .lifeline import build as build_life

SHICHEN = [("子", "23:30"), ("丑", "02:00"), ("寅", "04:00"), ("卯", "06:00"),
           ("辰", "08:00"), ("巳", "10:00"), ("午", "12:00"), ("未", "14:00"),
           ("申", "16:00"), ("酉", "18:00"), ("戌", "20:00"), ("亥", "22:00")]

# event wording -> which dimension should have moved that year
EVENT_DIM = {
    "婚": "婚恋", "恋": "婚恋", "离": "婚恋", "分手": "婚恋",
    "工作": "事业", "升职": "事业", "创业": "事业", "失业": "事业",
    "调动": "事业", "跳槽": "事业", "裁员": "事业",
    "财": "财富", "破财": "财富", "买房": "财富", "投资": "财富", "亏": "财富",
    "病": "健康", "手术": "健康", "意外": "健康", "住院": "健康",
    "考": "学业", "升学": "学业", "留学": "学业", "毕业": "学业", "读研": "学业",
    "搬": "人际", "出国": "人际", "合伙": "人际", "移居": "人际",
}


def classify(desc):
    for k, v in EVENT_DIM.items():
        if k in desc:
            return v
    return None


def _chart_args(solar, tm, args):
    return SimpleNamespace(
        solar=solar, lunar=None, time=tm, gender=args.gender,
        name="候选", city=getattr(args, "city", None),
        lon=getattr(args, "lon", None), no_tst=False, no_eot=False,
        hour_unknown=False, sect=getattr(args, "sect", 2))


def score_candidate(zhi, tm, args, events):
    chart = build_chart(_chart_args(args.solar, tm, args))
    life = build_life(chart, args.to_age, chart["meta"]["gender"])
    by_year = {r["year"]: r for r in life["years"]}

    total, detail = 0.0, []
    for ev in events:
        row = by_year.get(ev["year"])
        if not row:
            continue
        s, parts = 0.0, []
        if ev["dim"]:
            v = row["dims"][ev["dim"]]
            want = 1 if ev["valence"] >= 0 else -1
            s += v * want
            parts.append(f"{ev['dim']}{v:+.2f}×{want:+d}")
        majors = [e for e in row["events"] if e["level"] == "major"]
        s += 1.2 * len(majors)
        if majors:
            parts.append(f"结构事件{len(majors)}项({'/'.join(e['tag'] for e in majors)})")
        total += s
        detail.append({"year": ev["year"], "desc": ev["desc"], "dim": ev["dim"],
                       "contrib": round(s, 2), "why": "，".join(parts) or "无信号"})

    return {
        "zhi": zhi, "time": tm, "score": round(total, 2),
        "pillars": " ".join(p["ganzhi"] for p in chart["bazi"]["pillars"]),
        "day_master": chart["bazi"]["day_master"]["gan"],
        "strength": chart["bazi"]["strength"]["label"],
        "geju": f'{chart["bazi"]["geju"]["name"]}·{chart["bazi"]["geju"]["status"]}',
        "favor": chart["bazi"]["yongshen"]["favor"],
        "soul_palace": chart["ziwei"]["soul_palace_zhi"],
        "soul_star": chart["ziwei"]["soul_star"],
        "detail": detail,
        "_chart": chart, "_life": life,
    }


def rank(args, events):
    results = []
    for zhi, tm in SHICHEN:
        try:
            results.append(score_candidate(zhi, tm, args, events))
        except Exception as exc:
            print(f"  {zhi}时 失败: {exc}")
    results.sort(key=lambda r: -r["score"])

    top, second = results[0], results[1]
    margin = top["score"] - second["score"]
    spread = (top["score"] - results[-1]["score"]) or 1.0
    rel = margin / spread

    if rel >= 0.25 and len(events) >= 4:
        verdict = "可用"
        note = (f"{top['zhi']}时领先第二名 {margin:.2f}（占全距 {rel:.0%}），"
                f"可作为工作假设，但全文须标注时辰为反推所得。")
    elif rel >= 0.12:
        verdict = "待定"
        note = (f"{top['zhi']}时略微领先（占全距 {rel:.0%}）。"
                f"按 {top['zhi']}时 与 {second['zhi']}时 两套盘并行看，"
                f"只讲两盘都同意的部分，再补事件区分。")
    else:
        verdict = "不可用"
        note = (f"前两名差距仅占全距 {rel:.0%}，时辰没有被区分开。"
                f"不要挑一个假装知道——按时辰未知处理，"
                f"或补更多可确认、且分散在不同领域的事件。")
    return results, verdict, note, margin, rel


def run(args):
    raw = args.events
    if Path(raw).expanduser().exists():
        raw = Path(raw).expanduser().read_text(encoding="utf-8")
    events = json.loads(raw)
    for e in events:
        e.setdefault("valence", 0)
        e["dim"] = e.get("dim") or classify(e["desc"])

    if len(events) < 3:
        print("⚠ 少于 3 个事件，反推结果不可信。至少给 3 个，5 个以上才有区分度。")

    results, verdict, note, margin, rel = rank(args, events)

    workdir = Path(args.workdir).expanduser()
    workdir.mkdir(parents=True, exist_ok=True)
    for r in results:
        z = r["zhi"]
        (workdir / f"chart_{z}.json").write_text(
            json.dumps(r.pop("_chart"), ensure_ascii=False, indent=2),
            encoding="utf-8")
        (workdir / f"life_{z}.json").write_text(
            json.dumps(r.pop("_life"), ensure_ascii=False, indent=2),
            encoding="utf-8")
        r["chart_path"] = str(workdir / f"chart_{z}.json")
        r["lifeline_path"] = str(workdir / f"life_{z}.json")

    out = {"verdict": verdict, "note": note, "margin": round(margin, 2),
           "relative_margin": round(rel, 3), "events_used": events,
           "ranking": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    print(f"\n判定：{verdict} — {note}\n")
    for i, r in enumerate(results, 1):
        print(f"  {i:>2}. {r['zhi']}时 {r['score']:>+7.2f}  {r['pillars']}  "
              f"日主{r['day_master']}·{r['strength']}·{r['geju']}  "
              f"命宫{r['soul_palace']}·{r['soul_star']}")
    print(f"\n✓ {args.out}")
    return out
