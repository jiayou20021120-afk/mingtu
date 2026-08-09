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

# Event wording -> which dimension should have moved that year.
# Ordered longest-key-first at match time, so 「下岗」 beats a bare 「岗」 and
# 「离婚」 does not get read as 「离职」. The vocabulary leans deliberately
# towards the involuntary events a Chinese family actually remembers by year:
# 下岗, 参军, 分房, 拆迁 — these carry more signal than chosen ones.
EVENT_DIM = {
    "婚恋": {"结婚", "离婚", "订婚", "恋爱", "分手", "相亲", "领证", "再婚",
             "丧偶", "同居", "怀孕", "生子", "生孩子", "生育", "流产"},
    "事业": {"工作", "上班", "入职", "升职", "晋升", "创业", "失业", "下岗",
             "裁员", "辞职", "跳槽", "调动", "转行", "退休", "参军", "入伍",
             "转业", "复员", "开除", "提干", "评职称", "破产", "倒闭", "停薪"},
    "财富": {"破财", "买房", "购房", "分房", "拆迁", "投资", "亏损", "赔钱",
             "发财", "买车", "中奖", "欠债", "借钱", "还清", "financial", "财"},
    "健康": {"生病", "手术", "住院", "意外", "车祸", "受伤", "骨折", "确诊",
             "康复", "抑郁", "大病", "病"},
    "学业": {"高考", "中考", "考研", "考上", "升学", "留学", "毕业", "读研",
             "读博", "复读", "落榜", "考试", "考编", "考公", "进修", "考"},
    "人际": {"搬家", "出国", "移居", "移民", "合伙", "官司", "诉讼", "绝交",
             "和好", "认识", "搬"},
}
# longest keys first so specific wording wins over its own substring
_EVENT_KEYS = sorted(
    ((k, dim) for dim, ks in EVENT_DIM.items() for k in ks),
    key=lambda kv: -len(kv[0]))


def classify(desc):
    for key, dim in _EVENT_KEYS:
        if key in desc:
            return dim
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
