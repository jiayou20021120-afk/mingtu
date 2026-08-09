"""Single entry point: `mingtu`.

Sub-commands mirror the four layers — chart (L0/L1), life (L2), day (L2 fine
grain), render (presentation) — plus hour recovery and the calibration archive.
`mingtu full` runs the whole pipeline in one shot, which is what most people
actually want the first time.
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from . import __version__
from . import chart as chart_mod
from . import lifeline as life_mod
from . import yunshi as yunshi_mod
from . import hour as hour_mod
from . import render as render_mod
from . import profile as profile_mod


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _dump(obj, p):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                       encoding="utf-8")


def add_birth_args(p, require_gender=True):
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--solar", help="公历 YYYY-M-D")
    g.add_argument("--lunar", help="农历 YYYY-M-D")
    p.add_argument("--time", help="出生钟表时间 HH:MM（24 小时制）")
    p.add_argument("--gender", required=require_gender, help="男 / 女")
    p.add_argument("--name", default="命主")
    p.add_argument("--city", help="出生城市，用于真太阳时校正")
    p.add_argument("--lon", type=float, help="出生地经度，优先于 --city")
    p.add_argument("--no-tst", action="store_true", help="关闭真太阳时校正")
    p.add_argument("--no-eot", action="store_true", help="只做经度校正，不算均时差")
    p.add_argument("--hour-unknown", action="store_true", help="时辰不确定")
    p.add_argument("--sect", type=int, choices=(1, 2), default=2,
                   help="子时口径：2=晚子时法（默认）1=早子时法。"
                        "仅影响 23:00-24:00 出生者，但影响的是日主本身")


def cmd_chart(args):
    if not args.time:
        raise SystemExit("需要 --time。若确实不知道时辰，改用 `mingtu hour` 反推。")
    c = chart_mod.build(args)
    _dump(c, args.out)
    chart_mod.print_summary(c, args.out)
    return c


def cmd_life(args):
    c = _load(args.chart)
    out = life_mod.build(c, args.to_age, c["meta"]["gender"])
    _dump(out, args.out)
    life_mod.print_summary(out, args.out)
    return out


def cmd_day(args):
    c = _load(args.chart)
    target = (datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
              else date.today())
    res = yunshi_mod.build(c, target, args.span)
    if args.out:
        _dump(res, args.out)
    yunshi_mod.print_summary(c, res, target)
    return res


def cmd_hour(args):
    return hour_mod.run(args)


def cmd_render(args):
    html = render_mod.build_html(_load(args.chart), _load(args.lifeline),
                                 args.from_year, args.to_year)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"✓ {args.out}  ({len(html)//1024} KB)")


def cmd_full(args):
    outdir = Path(args.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    args.out = str(outdir / "chart.json")
    c = cmd_chart(args)

    life = life_mod.build(c, args.to_age, c["meta"]["gender"])
    _dump(life, outdir / "lifeline.json")
    print()
    life_mod.print_summary(life, str(outdir / "lifeline.json"))

    birth = life["meta"]["birth_year"]
    this_year = date.today().year
    f = args.from_year or max(birth, this_year - 8)
    t = args.to_year or f + 24
    html_path = outdir / f"{c['meta']['name']}-命途.html"
    html_path.write_text(render_mod.build_html(c, life, f, t), encoding="utf-8")
    print(f"\n✓ {html_path}")

    if args.today:
        print()
        res = yunshi_mod.build(c, date.today(), 1)
        _dump(res, outdir / "yunshi.json")
        yunshi_mod.print_summary(c, res, date.today())


def build_parser():
    ap = argparse.ArgumentParser(
        prog="mingtu",
        description="命途 — 八字与紫微斗数双轴人生全流程推演",
        epilog="文档与源码：https://github.com/jiayou20021120-afk/mingtu")
    ap.add_argument("--version", action="version", version=f"mingtu {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("full", help="一条命令跑完：排盘 + 时间轴 + HTML")
    add_birth_args(p)
    p.add_argument("--outdir", default="./mingtu-out")
    p.add_argument("--to-age", type=int, default=90)
    p.add_argument("--from-year", type=int)
    p.add_argument("--to-year", type=int)
    p.add_argument("--today", action="store_true", help="附带今日运势")
    p.set_defaults(func=cmd_full)

    p = sub.add_parser("chart", help="排盘 → chart.json")
    add_birth_args(p)
    p.add_argument("--out", default="chart.json")
    p.set_defaults(func=cmd_chart)

    p = sub.add_parser("life", help="人生全流程时间轴 → lifeline.json")
    p.add_argument("--chart", required=True)
    p.add_argument("--to-age", type=int, default=90)
    p.add_argument("--out", default="lifeline.json")
    p.set_defaults(func=cmd_life)

    p = sub.add_parser("day", help="流年/流月/流日运势")
    p.add_argument("--chart", required=True)
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--span", type=int, default=1, help="附带未来 N-1 天")
    p.add_argument("--out")
    p.set_defaults(func=cmd_day)

    p = sub.add_parser("hour", help="时辰未知时用已发生事件反推")
    p.add_argument("--solar", required=True)
    p.add_argument("--gender", required=True)
    p.add_argument("--city")
    p.add_argument("--lon", type=float)
    p.add_argument("--to-age", type=int, default=60)
    p.add_argument("--sect", type=int, choices=(1, 2), default=2)
    p.add_argument("--events", required=True,
                   help='JSON 文件或内联 JSON：[{"year":2015,"desc":"结婚","valence":1}]')
    p.add_argument("--workdir", default="./mingtu-out/hour")
    p.add_argument("--out", default="hour_ranking.json")
    p.set_defaults(func=cmd_hour)

    p = sub.add_parser("render", help="生成单文件 HTML 人生长卷")
    p.add_argument("--chart", required=True)
    p.add_argument("--lifeline", required=True)
    p.add_argument("--from-year", type=int)
    p.add_argument("--to-year", type=int)
    p.add_argument("--out", default="mingtu.html")
    p.set_defaults(func=cmd_render)

    profile_mod.register(sub)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit(130)
    return 0


if __name__ == "__main__":
    sys.exit(main())
