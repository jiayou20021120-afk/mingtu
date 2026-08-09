#!/usr/bin/env python3
"""L2: the life-arc timeline. This is what mingtu has that other tools don't.

Lays the Bazi luck-cycle axis and the Ziwei decade-limit axis onto one 0-90
year grid, scores every year on six dimensions from BOTH systems independently,
then reports where they agree (high confidence) and where they diverge (low).

Every number here comes from a rule in references/lifeline-rules.md. Nothing is
generated. The narrative layer reads this file; it does not recompute it.
"""
import argparse
import json
import sys

from lunar_python import Solar
import iztro_py

from .chart import (GAN_WUXING, ZHI_WUXING, HIDE_GAN, ZHI_CHONG,
                    ZHI_HE, ten_god, KE, zw_name)

DIMS = ["事业", "财富", "婚恋", "健康", "学业", "人际"]

# 十神 -> per-dimension relevance. Sign is set later by whether that element
# is a favourable or hostile element for this chart.
TENGOD_DIM = {
    "正官": {"事业": 3, "婚恋": 2, "人际": 1, "健康": -1},
    "七杀": {"事业": 2, "健康": -2, "人际": -1, "婚恋": 1},
    "正印": {"学业": 3, "事业": 1, "健康": 1, "人际": 1},
    "偏印": {"学业": 2, "健康": -1, "事业": 1},
    "比肩": {"人际": 2, "财富": -1, "事业": 1},
    "劫财": {"人际": 1, "财富": -2, "婚恋": -1},
    "食神": {"财富": 2, "健康": 2, "学业": 1, "婚恋": 1},
    "伤官": {"学业": 2, "事业": -2, "人际": -1, "财富": 1},
    "正财": {"财富": 3, "婚恋": 2, "健康": -1},
    "偏财": {"财富": 3, "人际": 2, "婚恋": 1},
}
# gendered: 男以财为妻, 女以官为夫
GENDER_MARRIAGE = {"男": ("正财", "偏财"), "女": ("正官", "七杀")}

# Each dimension is fed by a different number of ten-gods with different base
# magnitudes, so raw sums are not comparable across dimensions — without this
# the widest-fed dimension wins every cycle. Normalise by total feed, then
# apply a common gain so all six land on the same -5..+5 ruler.
def _dim_total(dim, gender):
    total = 0.0
    for god, row in TENGOD_DIM.items():
        v = abs(row.get(dim, 0))
        if dim == "婚恋" and god in GENDER_MARRIAGE[gender]:
            v *= 1.6
        total += v
    return total


DIM_TOTAL = {g: {d: _dim_total(d, g) for d in DIMS} for g in ("男", "女")}
DIM_GAIN = 11.0

DIM_PALACE = {
    "事业": ["官禄宫"], "财富": ["财帛宫"], "婚恋": ["夫妻宫"],
    "健康": ["疾厄宫"], "学业": ["父母宫", "官禄宫"], "人际": ["交友宫", "兄弟宫"],
}
SHA_STARS = {"擎羊", "陀罗", "火星", "铃星", "地空", "地劫"}
JI_STARS = {"左辅", "右弼", "文昌", "文曲", "天魁", "天钺", "禄存", "天马"}

MUTAGEN_WEIGHT = {"禄": 2.5, "权": 2.0, "科": 1.5, "忌": -3.0}

STAGE_BANDS = [(0, 15, "童蒙"), (16, 30, "立身"), (31, 45, "立业"),
               (46, 60, "中盘"), (61, 75, "收成"), (76, 120, "晚境")]


def chong_of(z):
    for a, b in ZHI_CHONG:
        if z == a:
            return b
        if z == b:
            return a
    return None


def he_of(z):
    for (a, b) in ZHI_HE:
        if z == a:
            return b
        if z == b:
            return a
    return None


def tian_ke(g1, g2):
    """True if g1 克 g2 across yin-yang (天克)."""
    return KE.get(GAN_WUXING[g1]) == GAN_WUXING[g2]


def polarity(elem, favor, avoid):
    if elem in favor:
        return 1.0
    if elem in avoid:
        return -1.0
    return 0.0


def element_flow(gan, zhi, favor, avoid):
    """Net favourable-element injection of a ganzhi, normalised to [-1, 1]."""
    total = 0.0
    weight = 0.0
    for e, w in [(GAN_WUXING[gan], 1.0)] + [(GAN_WUXING[g], w)
                                            for g, w in HIDE_GAN[zhi]]:
        weight += w
        if e in favor:
            total += w
        elif e in avoid:
            total -= w
    return round(total / weight, 3) if weight else 0.0


def bazi_year_dims(gan, zhi, day_gan, favor, avoid, gender):
    """Six-dimension score from the Bazi side. Range roughly -5..+5."""
    dims = {d: 0.0 for d in DIMS}
    contributors = []
    parts = [(gan, 1.0)] + [(g, w) for g, w in HIDE_GAN[zhi]]
    for g, w in parts:
        god = ten_god(day_gan, g)
        pol = polarity(GAN_WUXING[g], favor, avoid)
        for d, base in TENGOD_DIM.get(god, {}).items():
            eff = base * pol * w
            if d == "婚恋" and god in GENDER_MARRIAGE[gender]:
                eff *= 1.6
            dims[d] += eff
        contributors.append({"gan": g, "weight": w, "shishen": god,
                             "wuxing": GAN_WUXING[g],
                             "polarity": pol})
    norm = DIM_TOTAL[gender]
    return ({d: round(v / norm[d] * DIM_GAIN, 2) for d, v in dims.items()},
            contributors)


def natal_star_index(natal_palaces):
    """star name -> the natal palace index it sits in."""
    out = {}
    for p in natal_palaces:
        for s in p["major_stars"] + p["minor_stars"]:
            out[s["name"]] = p["index"]
    return out


def ziwei_scope_dims(scope, natal_palaces, star_idx=None, gain=1.0):
    """Six-dimension score for ANY horoscope scope — decadal, yearly, monthly
    or daily. They all carry the same shape: a rotated set of palace names plus
    four mutagen stars. Which natal palace a mutagen star sits in, and what that
    palace is *called* in this scope, is the whole mechanism.

    `gain` scales the result: a month or a day moves less than a year does.
    """
    star_idx = star_idx or natal_star_index(natal_palaces)
    idx_to_name = {i: zw_name(n, "palace")
                   for i, n in enumerate(scope.palace_names)}

    flying = []
    for label, key in zip(["禄", "权", "科", "忌"], scope.mutagen):
        sname = zw_name(key, "star")
        idx = star_idx.get(sname)
        flying.append({
            "mutagen": label, "star": sname,
            "natal_palace": next((p["name"] for p in natal_palaces
                                  if p["index"] == idx), None),
            "scope_palace": idx_to_name.get(idx),
        })

    dims = {d: 0.0 for d in DIMS}
    for f in flying:
        if f["scope_palace"] is None:
            continue
        w = MUTAGEN_WEIGHT[f["mutagen"]]
        for d, palaces in DIM_PALACE.items():
            if f["scope_palace"] in palaces:
                dims[d] += w
        if f["scope_palace"] == "命宫":
            for d in DIMS:
                dims[d] += w * 0.25

    # static modifier: 煞星 / 吉星 sitting in the natal palace that carries
    # this scope's relevant palace name
    by_name = {v: k for k, v in idx_to_name.items()}
    for d, palaces in DIM_PALACE.items():
        for pname in palaces:
            idx = by_name.get(pname)
            if idx is None:
                continue
            natal = next((p for p in natal_palaces if p["index"] == idx), None)
            if not natal:
                continue
            names = {s["name"] for s in natal["major_stars"] + natal["minor_stars"]}
            dims[d] -= 0.8 * len(names & SHA_STARS)
            dims[d] += 0.5 * len(names & JI_STARS)

    return ({d: round(v * gain, 2) for d, v in dims.items()}, flying,
            {"soul_palace_index": scope.index,
             "ganzhi": zw_name(scope.heavenly_stem, "stem")
             + zw_name(scope.earthly_branch, "branch"),
             "palace_by_index": idx_to_name})


def ziwei_year_dims(astro, natal_palaces, year, time_index):
    """Yearly wrapper — keeps the decadal context alongside the yearly score."""
    h = astro.horoscope(f"{year}-06-15", time_index)
    star_idx = natal_star_index(natal_palaces)
    dims, flying, meta = ziwei_scope_dims(h.yearly, natal_palaces, star_idx)
    _, _, dmeta = ziwei_scope_dims(h.decadal, natal_palaces, star_idx)
    for f in flying:                       # keep the old field names
        f["yearly_palace"] = f.pop("scope_palace")
        f["decadal_palace"] = dmeta["palace_by_index"].get(
            star_idx.get(f["star"]))
    return dims, flying, {
        "yearly_soul_palace_index": meta["soul_palace_index"],
        "yearly_ganzhi": meta["ganzhi"],
        "decadal_index": dmeta["soul_palace_index"],
        "decadal_ganzhi": dmeta["ganzhi"],
        "decadal_soul_palace": dmeta["palace_by_index"].get(
            dmeta["soul_palace_index"]),
        "nominal_age": h.nominal_age}


def detect_events(year, age, gz, dayun_gz, pillars, month_zhi, day_zhi,
                  xunkong, flying, day_gan, dayun_change):
    ev = []
    g, z = gz[0], gz[1]

    if dayun_change:
        ev.append({"tag": "换运", "level": "major",
                   "text": f"{year} 年进入 {dayun_gz} 运，前后一两年是过渡带，"
                           f"节奏和主题都会换轨"})
    if dayun_gz and gz == dayun_gz:
        ev.append({"tag": "岁运并临", "level": "major",
                   "text": f"流年 {gz} 与大运 {dayun_gz} 同字，力量叠加，"
                           f"该年主题被放到最大，好坏都加倍"})
    for p in pillars:
        if gz == p["ganzhi"]:
            ev.append({"tag": "伏吟", "level": "notable",
                       "text": f"流年 {gz} 与{p['pos']}柱同字（伏吟），"
                               f"{p['pos']}柱所主之事重演、旧事重提"})
        if tian_ke(g, p["gan"]) and chong_of(z) == p["zhi"]:
            ev.append({"tag": "反吟", "level": "major",
                       "text": f"流年 {gz} 天克地冲{p['pos']}柱 {p['ganzhi']}，"
                               f"该领域面临强制性变动"})
    if chong_of(z) == month_zhi:
        ev.append({"tag": "冲提纲", "level": "major",
                   "text": f"流年 {z} 冲月支 {month_zhi}，"
                           f"事业格局与所处环境容易整体挪位"})
    if chong_of(z) == day_zhi:
        ev.append({"tag": "冲日支", "level": "major",
                   "text": f"流年 {z} 冲日支 {day_zhi}（配偶宫），"
                           f"婚恋与自身状态是当年主戏"})
    if he_of(z) == day_zhi:
        ev.append({"tag": "合日支", "level": "notable",
                   "text": f"流年 {z} 合日支 {day_zhi}，感情与合作关系有牵引"})
    if z in xunkong:
        ev.append({"tag": "空亡", "level": "minor",
                   "text": f"流年 {z} 落本命旬空，投入容易见效慢，宜守成不宜开新局"})
    for f in flying:
        if f["mutagen"] == "忌" and f["yearly_palace"] in ("命宫", "夫妻宫", "疾厄宫"):
            ev.append({"tag": f"化忌入{f['yearly_palace']}", "level": "major",
                       "text": f"{f['star']}化忌落流年{f['yearly_palace']}，"
                               f"该宫位所主之事当年最耗心力"})
        elif f["mutagen"] == "忌" and f["yearly_palace"] in ("财帛宫", "官禄宫"):
            ev.append({"tag": f"化忌入{f['yearly_palace']}", "level": "notable",
                       "text": f"{f['star']}化忌落流年{f['yearly_palace']}，"
                               f"该方向当年投入产出比偏低"})
        if f["mutagen"] == "禄" and f["yearly_palace"] in (
                "命宫", "财帛宫", "官禄宫"):
            ev.append({"tag": f"化禄入{f['yearly_palace']}", "level": "notable",
                       "text": f"{f['star']}化禄落流年{f['yearly_palace']}，"
                               f"该方向当年最容易有实际收成"})
    return ev


# A year is a genuine turning point only when several structural signals stack
# in the same year, or when one of the heavyweight signals fires alone.
HEAVY_TAGS = {"岁运并临", "反吟", "换运"}


def turning_weight(events):
    majors = [e for e in events if e["level"] == "major"]
    w = sum(2 if e["tag"] in HEAVY_TAGS else 1 for e in majors)
    w += 0.5 * sum(1 for e in events if e["level"] == "notable")
    return w


def _confidence(agreement):
    """Two systems agreeing is the only thing that earns a high label. A year
    where they agree on three dimensions and contradict on three is not
    confident — it is ambiguous, and must read as such."""
    res = sum(1 for v in agreement.values() if v == "共振")
    con = sum(1 for v in agreement.values() if v == "冲突")
    if res >= 3 and con <= 1:
        return "高"
    if con >= 3 and res <= 1:
        return "低"
    if con >= 2 and res >= 2:
        return "分歧"
    return "中"


def stage_of(age):
    for lo, hi, name in STAGE_BANDS:
        if lo <= age <= hi:
            return name
    return "晚境"


def build(chart, to_age, gender):
    b = chart["bazi"]
    day_gan = b["day_master"]["gan"]
    favor = set(b["yongshen"]["favor"])
    avoid = set(b["yongshen"]["avoid"])
    pillars = b["pillars"]
    month_zhi, day_zhi = pillars[1]["zhi"], pillars[2]["zhi"]
    xunkong = b["xunkong"]

    birth_year = int(chart["meta"]["clock_time"][:4])
    eff = chart["meta"]["effective_time"]
    ti = chart["ziwei"]["time_index"]
    astro = iztro_py.by_solar(eff[:10], ti, gender)
    natal = chart["ziwei"]["palaces"]

    steps = chart["dayun"]["steps"]

    def step_for(age):
        cur = None
        for s in steps:
            if s["start_age"] <= age <= s["end_age"]:
                cur = s
        return cur

    rows = []
    for age in range(0, to_age + 1):
        year = birth_year + age
        gz = Solar.fromYmd(year, 6, 15).getLunar().getYearInGanZhi()
        st = step_for(age)
        dgz = st["ganzhi"] if st and st["gan"] else None

        ly, contrib = bazi_year_dims(gz[0], gz[1], day_gan, favor, avoid, gender)
        # The luck cycle carries its own six-dimension profile and sets the
        # decade's baseline; the year modulates it. Ratio 40/60 — a good year
        # inside a hostile cycle stays capped, which is how it actually works.
        if dgz:
            dy_dims, _ = bazi_year_dims(dgz[0], dgz[1], day_gan, favor, avoid, gender)
            dy_flow = element_flow(dgz[0], dgz[1], favor, avoid)
            phase = "天干段" if age - st["start_age"] < 5 else "地支段"
            seg = dgz[0] if phase == "天干段" else dgz[1]
            seg_elem = GAN_WUXING[seg] if phase == "天干段" else ZHI_WUXING[seg]
            seg_bias = polarity(seg_elem, favor, avoid)
            bd = {d: round(ly[d] * 0.6 + dy_dims[d] * 0.4 + seg_bias * 0.3, 2)
                  for d in DIMS}
        else:
            bd, dy_flow, phase, seg_bias = dict(ly), 0.0, "起运前", 0.0

        try:
            zd, flying, zmeta = ziwei_year_dims(astro, natal, year, ti)
        except Exception as e:                       # far-out years
            zd = {d: 0.0 for d in DIMS}
            flying, zmeta = [], {"error": str(e)}

        combined, agreement = {}, {}
        for d in DIMS:
            combined[d] = round((bd[d] + zd[d]) / 2, 2)
            if abs(bd[d]) < 1 and abs(zd[d]) < 1:
                agreement[d] = "平"
            elif bd[d] * zd[d] > 0:
                agreement[d] = "共振"
            elif bd[d] * zd[d] < 0:
                agreement[d] = "冲突"
            else:
                agreement[d] = "单边"

        dayun_change = bool(st and age == st["start_age"] and st["gan"])
        events = detect_events(year, age, gz, dgz, pillars, month_zhi, day_zhi,
                               xunkong, flying, day_gan, dayun_change)

        rows.append({
            "age": age, "nominal_age": age + 1, "year": year, "ganzhi": gz,
            "stage": stage_of(age),
            "dayun": {"ganzhi": dgz, "start_age": st["start_age"] if st else None,
                      "shishen": st["shishen_gan"] if st else None,
                      "phase": phase, "flow": dy_flow},
            "ziwei_cycle": zmeta,
            "bazi_dims": bd, "ziwei_dims": zd,
            "dims": combined, "agreement": agreement,
            "agreement_counts": {
                k: sum(1 for v in agreement.values() if v == k)
                for k in ("共振", "冲突", "单边", "平")},
            "score": round(sum(combined.values()) / len(DIMS), 2),
            "confidence": _confidence(agreement),
            "shishen_gan": ten_god(day_gan, gz[0]),
            "shishen_zhi": ten_god(day_gan, HIDE_GAN[gz[1]][0][0]),
            "flying_mutagen": flying,
            "events": events,
            "contributors": contrib,
        })

    # per-decade summary on the Bazi luck-cycle axis
    step_summary = []
    for s in steps:
        sub = [r for r in rows if s["start_age"] <= r["age"] <= s["end_age"]]
        if not sub:
            continue
        dims_avg = {d: round(sum(r["dims"][d] for r in sub) / len(sub), 2)
                    for d in DIMS}
        step_summary.append({
            "ganzhi": s["ganzhi"], "shishen": s["shishen_gan"],
            "age_range": [s["start_age"], s["end_age"]],
            "year_range": [s["start_year"], s["end_year"]],
            "flow": element_flow(s["gan"], s["zhi"], favor, avoid) if s["gan"] else 0.0,
            "dims": dims_avg,
            "score": round(sum(dims_avg.values()) / len(DIMS), 2),
            "peak_years": [r["year"] for r in sorted(sub, key=lambda r: -r["score"])[:2]],
            "trough_years": [r["year"] for r in sorted(sub, key=lambda r: r["score"])[:2]],
            "major_events": [e for r in sub for e in r["events"]
                             if e["level"] == "major"][:4],
            "dominant_dimension": max(dims_avg, key=dims_avg.get),
            "weakest_dimension": min(dims_avg, key=dims_avg.get),
        })

    # Absolute scores are not comparable between people — a chart with three
    # favourable elements runs positive everywhere. What a reader actually
    # needs is where a cycle sits within their OWN ten steps.
    scored = [s for s in step_summary if s["ganzhi"] != "(起运前)"]
    lo = min(s["score"] for s in scored)
    hi = max(s["score"] for s in scored)
    span = (hi - lo) or 1.0
    for rank, s in enumerate(sorted(scored, key=lambda x: -x["score"]), 1):
        s["rank"] = rank
        s["rank_of"] = len(scored)
        s["relative"] = round((s["score"] - lo) / span, 3)

    ys = sorted(r["score"] for r in rows)
    for r in rows:
        below = sum(1 for v in ys if v < r["score"])
        r["percentile_in_life"] = round(below / len(ys), 3)

    # Pick highlights from the span a reader will actually live through;
    # a peak cycle starting at 89 is technically true and practically useless.
    livable = [s for s in scored if s["age_range"][0] <= 80] or scored
    golden = sorted(livable, key=lambda s: -s["score"])[:2]
    hard = sorted(livable, key=lambda s: s["score"])[:2]

    return {
        "meta": {
            "name": chart["meta"]["name"], "gender": gender,
            "birth_year": birth_year, "to_age": to_age,
            "favor": sorted(favor), "avoid": sorted(avoid),
            "method": chart["bazi"]["yongshen"]["method"],
            "geju": chart["bazi"]["geju"]["name"],
            "strength": chart["bazi"]["strength"]["label"],
            "hour_known": chart["meta"]["hour_known"],
            "scale_note": "维度分区间 -5..+5，0 为平；分数是结构性倾向，不是概率",
        },
        "overview": {
            "golden_cycles": [{"ganzhi": s["ganzhi"], "ages": s["age_range"],
                               "years": s["year_range"], "score": s["score"],
                               "dominant": s["dominant_dimension"]} for s in golden],
            "hard_cycles": [{"ganzhi": s["ganzhi"], "ages": s["age_range"],
                             "years": s["year_range"], "score": s["score"],
                             "weakest": s["weakest_dimension"]} for s in hard],
            "turning_points": sorted(
                [{"year": r["year"], "age": r["age"],
                  "weight": turning_weight(r["events"]),
                  "score": r["score"],
                  "tags": [e["tag"] for e in r["events"] if e["level"] == "major"]}
                 for r in rows if turning_weight(r["events"]) >= 3],
                key=lambda t: (-t["weight"], t["year"]))[:15],
        },
        "cycles": step_summary,
        "years": rows,
    }


def print_summary(out, out_path=None):
    if out_path:
        print(f"✓ {out_path}  {len(out['years'])} 年 / {len(out['cycles'])} 步大运")
    for c in out["cycles"]:
        if c["ganzhi"] == "(起运前)":
            continue
        bar = "█" * max(1, int(round(c["relative"] * 12)))
        print(f"  {c['age_range'][0]:>2}-{c['age_range'][1]:<2}岁 "
              f"{c['ganzhi']}({c['shishen'] or '—'}) {c['score']:>+5.2f} "
              f"#{c['rank']}/{c['rank_of']} {bar:<12} "
              f"强:{c['dominant_dimension']} 弱:{c['weakest_dimension']}")
    tp = out["overview"]["turning_points"]
    if tp:
        print(f"  关键转折 {len(tp)} 处："
              f"{', '.join(str(t['year']) for t in tp[:8])}")
    else:
        print("  未检出强结构性转折年份（盘面平稳）")
