#!/usr/bin/env python3
"""Day / month / year fortune — the everyday entry point.

The life arc answers "what shape is my life". This answers "what about this
week". Same four scoring layers, finer granularity: the year sets the ceiling,
the month bends it, the day only nudges. Weights below encode exactly that, so
a good day inside a hostile year never reads as a green light.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta

from lunar_python import Solar
import iztro_py

from .lifeline import (DIMS, bazi_year_dims, ziwei_scope_dims, natal_star_index,
                      _confidence, chong_of, he_of)
from .chart import HIDE_GAN, ten_god, GAN_WUXING

# A year outweighs a month outweighs a day. Anyone telling you today alone
# decides something is selling you something.
SCOPE_WEIGHT = {"yearly": 1.0, "monthly": 0.55, "daily": 0.3}


def scope_ganzhi(d: date, scope: str) -> str:
    lunar = Solar.fromYmd(d.year, d.month, d.day).getLunar()
    return {"yearly": lunar.getYearInGanZhi,
            "monthly": lunar.getMonthInGanZhi,
            "daily": lunar.getDayInGanZhi}[scope]()


def analyse(chart, target: date, scope: str):
    b = chart["bazi"]
    day_gan = b["day_master"]["gan"]
    favor, avoid = set(b["yongshen"]["favor"]), set(b["yongshen"]["avoid"])
    gender = chart["meta"]["gender"]
    natal = chart["ziwei"]["palaces"]
    ti = chart["ziwei"]["time_index"]
    eff = chart["meta"]["effective_time"]

    astro = iztro_py.by_solar(eff[:10], ti, gender)
    h = astro.horoscope(target.strftime("%Y-%m-%d"), ti)
    star_idx = natal_star_index(natal)

    gz = scope_ganzhi(target, scope)
    bd, contrib = bazi_year_dims(gz[0], gz[1], day_gan, favor, avoid, gender)
    w = SCOPE_WEIGHT[scope]
    bd = {d: round(v * w, 2) for d, v in bd.items()}

    zsrc = getattr(h, scope)
    zd, flying, zmeta = ziwei_scope_dims(zsrc, natal, star_idx, gain=w)

    combined, agreement = {}, {}
    for d in DIMS:
        combined[d] = round((bd[d] + zd[d]) / 2, 2)
        if abs(bd[d]) < 0.5 and abs(zd[d]) < 0.5:
            agreement[d] = "平"
        elif bd[d] * zd[d] > 0:
            agreement[d] = "共振"
        elif bd[d] * zd[d] < 0:
            agreement[d] = "冲突"
        else:
            agreement[d] = "单边"

    # structural contact with the natal chart
    month_zhi, day_zhi = b["pillars"][1]["zhi"], b["pillars"][2]["zhi"]
    notes = []
    if chong_of(gz[1]) == day_zhi:
        notes.append(f"{gz[1]} 冲日支 {day_zhi}，自身与亲密关系是主戏")
    if he_of(gz[1]) == day_zhi:
        notes.append(f"{gz[1]} 合日支 {day_zhi}，关系与合作有牵引")
    if chong_of(gz[1]) == month_zhi:
        notes.append(f"{gz[1]} 冲月支 {month_zhi}，工作环境与位置容易动")
    if gz[1] in b["xunkong"]:
        notes.append(f"{gz[1]} 落本命旬空，投入见效偏慢")
    for f in flying:
        if f["mutagen"] == "忌" and f["scope_palace"]:
            notes.append(f"{f['star']}化忌落{f['scope_palace']}，此处最耗心力")
        if f["mutagen"] == "禄" and f["scope_palace"]:
            notes.append(f"{f['star']}化禄落{f['scope_palace']}，此处最容易见实效")

    return {
        "scope": scope, "date": target.isoformat(), "ganzhi": gz,
        "weight": w,
        "shishen_gan": ten_god(day_gan, gz[0]),
        "shishen_zhi": ten_god(day_gan, HIDE_GAN[gz[1]][0][0]),
        "wuxing_gan": GAN_WUXING[gz[0]],
        "bazi_dims": bd, "ziwei_dims": zd, "dims": combined,
        "agreement": agreement, "confidence": _confidence(agreement),
        "score": round(sum(combined.values()) / len(DIMS), 2),
        "best": max(combined, key=combined.get),
        "worst": min(combined, key=combined.get),
        "ziwei": zmeta, "flying_mutagen": flying,
        "notes": notes, "contributors": contrib,
    }


def build(chart, target: date, span: int):
    out = {
        "meta": {
            "name": chart["meta"]["name"], "gender": chart["meta"]["gender"],
            "target": target.isoformat(),
            "favor": chart["bazi"]["yongshen"]["favor"],
            "avoid": chart["bazi"]["yongshen"]["avoid"],
            "scale_note": "年 1.0 / 月 0.55 / 日 0.3 加权。"
                          "日的权重最低是有意的：一天不决定什么。",
        },
        "year": analyse(chart, target, "yearly"),
        "month": analyse(chart, target, "monthly"),
        "day": analyse(chart, target, "daily"),
    }
    if span > 1:
        out["upcoming"] = [analyse(chart, target + timedelta(days=i), "daily")
                           for i in range(1, span)]
    # what the stack actually says, once weighted
    stacked = {d: round(out["year"]["dims"][d] + out["month"]["dims"][d]
                        + out["day"]["dims"][d], 2) for d in DIMS}
    out["stacked"] = {
        "dims": stacked,
        "score": round(sum(stacked.values()) / len(DIMS), 2),
        "best": max(stacked, key=stacked.get),
        "worst": min(stacked, key=stacked.get),
        "dominated_by": max(("year", "month", "day"),
                            key=lambda k: abs(out[k]["score"])),
    }
    return out


def print_summary(chart, res, target):
    def line(tag, r):
        return (f"  {tag} {r['ganzhi']}({r['shishen_gan']}) "
                f"{r['score']:>+5.2f}  \u5f3a:{r['best']} \u5f31:{r['worst']}  "
                f"\u4e00\u81f4\u5ea6:{r['confidence']}")
    print(f"{chart['meta']['name']} \u00b7 {target.isoformat()}")
    print(line("\u6d41\u5e74", res["year"]))
    print(line("\u6d41\u6708", res["month"]))
    print(line("\u6d41\u65e5", res["day"]))
    s = res["stacked"]
    print(f"  \u53e0\u52a0  \u5f3a:{s['best']} {s['dims'][s['best']]:+.2f}  "
          f"\u5f31:{s['worst']} {s['dims'][s['worst']]:+.2f}  "
          f"\u4e3b\u5bfc\u5c42:{s['dominated_by']}")
    for n in res["day"]["notes"][:4]:
        print(f"  \u00b7 {n}")
    for u in res.get("upcoming", []):
        print(f"  {u['date']} {u['ganzhi']} {u['score']:+.2f} "
              f"\u5f3a:{u['best']} \u5f31:{u['worst']}")
