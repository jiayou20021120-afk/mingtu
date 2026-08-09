"""Calibration archive: remember which predictions landed and which didn't.

Every other tool asks its calibration questions, hears the answer, and throws it
away. A chart that has been checked against five real events is worth more than
one that hasn't, and that difference should survive the session.

This also does the part a plain JSON writer wouldn't: when a dimension misses
repeatedly, or when hits and misses invert, it says so and proposes the
adjustment rather than leaving you to notice.
"""
import json
import os
import re
from datetime import date
from pathlib import Path

VERDICTS = ("命中", "部分", "落空")
DIMS = ["事业", "财富", "婚恋", "健康", "学业", "人际"]


def profiles_dir() -> Path:
    d = Path(os.environ.get("MINGTU_HOME", Path.home() / ".mingtu")) / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def slugify(name: str) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "-", name.strip()).strip("-").lower()
    return s or "unnamed"


def path_for(slug: str) -> Path:
    return profiles_dir() / f"{slug}.json"


def load(slug: str):
    p = path_for(slug)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(prof: dict) -> Path:
    prof["last_updated"] = date.today().isoformat()
    prof["summary"] = summarise(prof)
    prof["adjustments"] = suggest(prof)
    p = path_for(prof["slug"])
    p.write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def create(name, solar=None, lunar=None, time=None, gender=None, city=None,
           hour_source="用户提供", hour_confidence="确定",
           chart_path=None, lifeline_path=None, slug=None):
    return {
        "slug": slug or slugify(name),
        "name": name,
        "input": {"solar": solar, "lunar": lunar, "time": time,
                  "gender": gender, "city": city, "hour_source": hour_source},
        "hour_confidence": hour_confidence,
        "chart_path": chart_path, "lifeline_path": lifeline_path,
        "calibration": [], "adjustments": [], "summary": {},
    }


def add_calibration(prof, year, predicted, actual, verdict, dim=None, note=""):
    if verdict not in VERDICTS:
        raise ValueError(f"verdict 必须是 {VERDICTS} 之一")
    prof.setdefault("calibration", []).append({
        "year": int(year), "dim": dim, "predicted": predicted,
        "actual": actual, "verdict": verdict, "note": note,
        "recorded": date.today().isoformat(),
    })
    return prof


def summarise(prof):
    cal = prof.get("calibration", [])
    if not cal:
        return {"n": 0, "note": "尚未校准。未校准的盘准确率大致六到七成。"}
    counts = {v: sum(1 for c in cal if c["verdict"] == v) for v in VERDICTS}
    n = len(cal)
    score = (counts["命中"] + 0.5 * counts["部分"]) / n
    by_dim = {}
    for c in cal:
        if not c.get("dim"):
            continue
        d = by_dim.setdefault(c["dim"], {v: 0 for v in VERDICTS})
        d[c["verdict"]] += 1
    return {
        "n": n, "counts": counts, "hit_rate": round(score, 3),
        "by_dimension": by_dim,
        "grade": ("已校准·可信" if n >= 5 and score >= 0.6
                  else "已校准·存疑" if n >= 5
                  else "校准不足"),
    }


def suggest(prof):
    """Turn the record into concrete next actions, per calibration.md §3."""
    cal = prof.get("calibration", [])
    s = summarise(prof)
    out = []
    if s["n"] == 0:
        return out

    for dim, c in s.get("by_dimension", {}).items():
        if c["落空"] >= 3:
            out.append(f"{dim}维度连续落空 {c['落空']} 次，下调该维度解读权重")
        elif c["命中"] >= 3 and c["落空"] == 0:
            out.append(f"{dim}维度 {c['命中']} 次命中零落空，该维度判读可信")

    if s["n"] >= 4 and s["hit_rate"] <= 0.25:
        out.append("整体命中率过低。按 calibration.md §3，优先重查用神"
                   "（身强身弱判反是最常见根因），其次重查时辰")

    years = sorted(c["year"] for c in cal if c["verdict"] in ("命中", "部分"))
    if len(years) >= 3:
        gaps = [c.get("note", "") for c in cal
                if "偏" in c.get("note", "") or "差" in c.get("note", "")]
        if len(gaps) >= 2:
            out.append("多条记录提到时间偏移，检查起运岁数与真太阳时校正")

    if prof.get("hour_confidence", "").startswith("反推") and s["hit_rate"] < 0.5:
        out.append("时辰为反推所得且命中率偏低，建议补事件重跑 mingtu hour")
    return out


# ---------------------------------------------------------------- CLI

def cmd_save(args):
    prof = load(args.slug) if args.slug and load(args.slug) else None
    if prof is None:
        prof = create(args.name or args.slug, solar=args.solar, lunar=args.lunar,
                      time=args.time, gender=args.gender, city=args.city,
                      hour_source=args.hour_source,
                      hour_confidence=args.hour_confidence, slug=args.slug)
    else:
        for k, v in (("solar", args.solar), ("lunar", args.lunar),
                     ("time", args.time), ("gender", args.gender),
                     ("city", args.city)):
            if v:
                prof["input"][k] = v
        if args.name:
            prof["name"] = args.name
        if args.hour_confidence:
            prof["hour_confidence"] = args.hour_confidence
    if args.chart:
        prof["chart_path"] = str(Path(args.chart).resolve())
    if args.lifeline:
        prof["lifeline_path"] = str(Path(args.lifeline).resolve())
    p = save(prof)
    print(f"✓ {p}")
    return prof


def cmd_calibrate(args):
    prof = load(args.slug)
    if prof is None:
        raise SystemExit(f"没有档案 {args.slug}，先跑 mingtu profile save")
    add_calibration(prof, args.year, args.predicted, args.actual,
                    args.verdict, args.dim, args.note or "")
    p = save(prof)
    s = prof["summary"]
    print(f"✓ {p}")
    print(f"  已记 {s['n']} 条，命中率 {s['hit_rate']:.0%}（{s['grade']}）")
    for a in prof["adjustments"]:
        print(f"  → {a}")


def cmd_show(args):
    prof = load(args.slug)
    if prof is None:
        raise SystemExit(f"没有档案 {args.slug}")
    print(json.dumps(prof, ensure_ascii=False, indent=2))


def cmd_list(args):
    rows = []
    for f in sorted(profiles_dir().glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        s = p.get("summary") or summarise(p)
        rows.append((p["slug"], p.get("name", ""),
                     p.get("input", {}).get("solar") or p.get("input", {}).get("lunar") or "-",
                     s.get("n", 0), s.get("grade", "-"),
                     p.get("last_updated", "-")))
    if not rows:
        print(f"（{profiles_dir()} 下暂无档案）")
        return
    print(f"{'slug':<18}{'姓名':<10}{'生辰':<13}{'校准':<6}{'状态':<14}更新")
    for r in rows:
        print(f"{r[0]:<18}{r[1]:<10}{r[2]:<13}{r[3]:<6}{r[4]:<14}{r[5]}")


def register(sub):
    p = sub.add_parser("profile", help="校准档案：记录哪些推断兑现了")
    ps = p.add_subparsers(dest="sub", required=True)

    a = ps.add_parser("save", help="新建或更新档案")
    a.add_argument("--slug", required=True)
    a.add_argument("--name")
    a.add_argument("--solar")
    a.add_argument("--lunar")
    a.add_argument("--time")
    a.add_argument("--gender")
    a.add_argument("--city")
    a.add_argument("--chart")
    a.add_argument("--lifeline")
    a.add_argument("--hour-source", default="用户提供")
    a.add_argument("--hour-confidence", default="确定",
                   help="确定 / 反推(可用) / 反推(待定) / 未知")
    a.set_defaults(func=cmd_save)

    b = ps.add_parser("calibrate", help="记录一条推断的验证结果")
    b.add_argument("--slug", required=True)
    b.add_argument("--year", type=int, required=True)
    b.add_argument("--predicted", required=True)
    b.add_argument("--actual", required=True)
    b.add_argument("--verdict", required=True, choices=VERDICTS)
    b.add_argument("--dim", choices=DIMS)
    b.add_argument("--note")
    b.set_defaults(func=cmd_calibrate)

    c = ps.add_parser("show", help="打印档案 JSON")
    c.add_argument("--slug", required=True)
    c.set_defaults(func=cmd_show)

    d = ps.add_parser("list", help="列出全部档案")
    d.set_defaults(func=cmd_list)
