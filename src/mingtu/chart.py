#!/usr/bin/env python3
"""L0 + L1: deterministic chart computation. Bazi (lunar-python) + Ziwei (iztro-py).

Emits chart.json. No LLM involvement anywhere in this file — every field is
either a calendar fact or the output of an explicitly documented rule.
Rule provenance is tagged per field so the narrative layer can label confidence.
"""
import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta

from lunar_python import Lunar, Solar

import iztro_py
from iztro_py.i18n.locales import zh_CN

# ---------------------------------------------------------------- constants

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"

GAN_WUXING = dict(zip(GAN, "木木火火土土金金水水"))
GAN_YINYANG = dict(zip(GAN, [1, -1] * 5))
ZHI_WUXING = dict(zip(ZHI, "水土木木土火火土金金土水"))

HIDE_GAN = {
    "子": [("癸", 0.6)],
    "丑": [("己", 0.6), ("癸", 0.3), ("辛", 0.1)],
    "寅": [("甲", 0.6), ("丙", 0.3), ("戊", 0.1)],
    "卯": [("乙", 0.6)],
    "辰": [("戊", 0.6), ("乙", 0.3), ("癸", 0.1)],
    "巳": [("丙", 0.6), ("庚", 0.3), ("戊", 0.1)],
    "午": [("丁", 0.6), ("己", 0.3)],
    "未": [("己", 0.6), ("丁", 0.3), ("乙", 0.1)],
    "申": [("庚", 0.6), ("壬", 0.3), ("戊", 0.1)],
    "酉": [("辛", 0.6)],
    "戌": [("戊", 0.6), ("辛", 0.3), ("丁", 0.1)],
    "亥": [("壬", 0.6), ("甲", 0.3)],
}

SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

GAN_HE = {("甲", "己"): "土", ("乙", "庚"): "金", ("丙", "辛"): "水",
          ("丁", "壬"): "木", ("戊", "癸"): "火"}
ZHI_HE = {("子", "丑"): "土", ("寅", "亥"): "木", ("卯", "戌"): "火",
          ("辰", "酉"): "金", ("巳", "申"): "水", ("午", "未"): "土"}
ZHI_CHONG = [("子", "午"), ("丑", "未"), ("寅", "申"),
             ("卯", "酉"), ("辰", "戌"), ("巳", "亥")]
SAN_HE = {("申", "子", "辰"): "水", ("亥", "卯", "未"): "木",
          ("寅", "午", "戌"): "火", ("巳", "酉", "丑"): "金"}
SAN_HUI = {("亥", "子", "丑"): "水", ("寅", "卯", "辰"): "木",
           ("巳", "午", "未"): "火", ("申", "酉", "戌"): "金"}
XING_GROUPS = [(("寅", "巳", "申"), "无恩之刑"), (("丑", "戌", "未"), "恃势之刑")]
XING_PAIRS = [(("子", "卯"), "无礼之刑")]
SELF_XING = ["辰", "午", "酉", "亥"]
ZHI_HAI = [("子", "未"), ("丑", "午"), ("寅", "巳"),
           ("卯", "辰"), ("申", "亥"), ("酉", "戌")]

# month branch -> season, for 调候 gating
WINTER_ZHI = {"亥", "子", "丑"}
SUMMER_ZHI = {"巳", "午", "未"}

TIANYI = {"甲": "丑未", "戊": "丑未", "庚": "丑未", "乙": "子申", "己": "子申",
          "丙": "亥酉", "丁": "亥酉", "壬": "卯巳", "癸": "卯巳", "辛": "寅午"}
WENCHANG = dict(zip(GAN, ["巳", "午", "申", "酉", "申", "酉", "亥", "子", "寅", "卯"]))
YANGREN = {"甲": "卯", "乙": "寅", "丙": "午", "丁": "巳", "戊": "午",
           "己": "巳", "庚": "酉", "辛": "申", "壬": "子", "癸": "亥"}
JINYU = dict(zip(GAN, ["辰", "巳", "未", "申", "未", "申", "戌", "亥", "丑", "寅"]))
KUIGANG = {"庚辰", "庚戌", "壬辰", "戊戌"}
TRIAD_OF = {}
for trio, elem in SAN_HE.items():
    for z in trio:
        TRIAD_OF[z] = trio
TAOHUA = {("寅", "午", "戌"): "卯", ("申", "子", "辰"): "酉",
          ("巳", "酉", "丑"): "午", ("亥", "卯", "未"): "子"}
YIMA = {("寅", "午", "戌"): "申", ("申", "子", "辰"): "寅",
        ("巳", "酉", "丑"): "亥", ("亥", "卯", "未"): "巳"}
HUAGAI = {("寅", "午", "戌"): "戌", ("申", "子", "辰"): "辰",
          ("巳", "酉", "丑"): "丑", ("亥", "卯", "未"): "未"}
GUCHEN_GUASU = {
    frozenset("亥子丑"): ("寅", "戌"), frozenset("寅卯辰"): ("巳", "丑"),
    frozenset("巳午未"): ("申", "辰"), frozenset("申酉戌"): ("亥", "未"),
}

# longitudes for real-solar-time correction
CITY_LON = {
    "北京": 116.41, "上海": 121.47, "广州": 113.26, "深圳": 114.06, "天津": 117.20,
    "重庆": 106.55, "成都": 104.07, "杭州": 120.15, "南京": 118.80, "武汉": 114.31,
    "西安": 108.95, "沈阳": 123.43, "哈尔滨": 126.53, "长春": 125.32, "大连": 121.62,
    "济南": 117.00, "青岛": 120.38, "郑州": 113.62, "长沙": 112.94, "南昌": 115.89,
    "合肥": 117.28, "福州": 119.30, "厦门": 118.09, "昆明": 102.83, "贵阳": 106.63,
    "南宁": 108.37, "海口": 110.20, "兰州": 103.82, "西宁": 101.78, "银川": 106.28,
    "乌鲁木齐": 87.62, "拉萨": 91.11, "呼和浩特": 111.75, "太原": 112.55,
    "石家庄": 114.51, "苏州": 120.59, "宁波": 121.55, "温州": 120.70, "无锡": 120.30,
    "东莞": 113.75, "佛山": 113.12, "泉州": 118.58, "汕头": 116.68, "洛阳": 112.45,
    "香港": 114.17, "澳门": 113.55, "台北": 121.52, "丹东": 124.38, "徐州": 117.28,
}

ZW = zh_CN.translations


def zw_name(key, kind):
    """Translate an iztro internal key to Chinese."""
    if key is None:
        return None
    if kind == "palace":
        return ZW["palaces"].get(key, key)
    if kind == "stem":
        return ZW["heavenlyStem"].get(key, key)
    if kind == "branch":
        return ZW["earthlyBranch"].get(key, key)
    for bucket in ("major", "minor"):
        if key in ZW["stars"].get(bucket, {}):
            return ZW["stars"][bucket][key]
    for k, v in ZW.items():
        if isinstance(v, dict):
            if key in v:
                return v[key]
            for vv in v.values():
                if isinstance(vv, dict) and key in vv:
                    return vv[key]
    return key


# ---------------------------------------------------------------- solar time

def equation_of_time(d: date) -> float:
    """Minutes the true sun leads the mean sun. Standard approximation."""
    n = d.timetuple().tm_yday
    b = 2 * math.pi * (n - 81) / 364.0
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def apply_true_solar_time(dt: datetime, lon: float, use_eot: bool):
    lon_min = (lon - 120.0) * 4.0
    eot_min = equation_of_time(dt.date()) if use_eot else 0.0
    total = lon_min + eot_min
    return dt + timedelta(minutes=total), lon_min, eot_min


def shichen_of(dt: datetime) -> str:
    h = dt.hour
    return ZHI[((h + 1) // 2) % 12]


# ---------------------------------------------------------------- ten gods

def ten_god(day_gan: str, other: str) -> str:
    dw, ow = GAN_WUXING[day_gan], GAN_WUXING[other]
    same = GAN_YINYANG[day_gan] == GAN_YINYANG[other]
    if dw == ow:
        return "比肩" if same else "劫财"
    if SHENG[ow] == dw:
        return "偏印" if same else "正印"
    if SHENG[dw] == ow:
        return "食神" if same else "伤官"
    if KE[ow] == dw:
        return "七杀" if same else "正官"
    return "偏财" if same else "正财"


TEN_GOD_GROUP = {
    "比肩": "比劫", "劫财": "比劫", "食神": "食伤", "伤官": "食伤",
    "正财": "财", "偏财": "财", "正官": "官杀", "七杀": "官杀",
    "正印": "印", "偏印": "印",
}


# ---------------------------------------------------------------- five-element scoring

def score_wuxing(pillars, month_zhi, day_zhi, chong_zhi):
    """Weighted element tally. Weights documented in references/ganzhi-tables.md §6."""
    score = {e: 0.0 for e in "木火土金水"}
    detail = []
    for p in pillars:
        score[GAN_WUXING[p["gan"]]] += 1.0
        detail.append((p["pos"] + "干", p["gan"], GAN_WUXING[p["gan"]], 1.0))
        mult = 1.0
        if p["pos"] == "月":
            mult *= 1.5
        if p["pos"] == "日":
            mult *= 1.2
        if p["zhi"] in chong_zhi:
            mult *= 0.6
        for g, w in HIDE_GAN[p["zhi"]]:
            v = w * mult
            score[GAN_WUXING[g]] += v
            detail.append((p["pos"] + "支藏", g, GAN_WUXING[g], round(v, 3)))
    return {k: round(v, 3) for k, v in score.items()}, detail


def judge_strength(day_gan, month_zhi, day_zhi, pillars, wuxing, chong_zhi):
    dw = GAN_WUXING[day_gan]
    total = sum(wuxing.values()) or 1.0

    month_main = HIDE_GAN[month_zhi][0][0]
    mw = GAN_WUXING[month_main]
    if mw == dw:
        deling, deling_txt = 1.0, "当令"
    elif SHENG[mw] == dw:
        deling, deling_txt = 0.7, "得生（相）"
    elif SHENG[dw] == mw:
        deling, deling_txt = 0.3, "泄气（休）"
    elif KE[dw] == mw:
        deling, deling_txt = 0.2, "耗气（囚）"
    else:
        deling, deling_txt = 0.0, "受克（死）"

    roots = []
    for p in pillars:
        for g, w in HIDE_GAN[p["zhi"]]:
            if GAN_WUXING[g] == dw:
                roots.append(f"{p['pos']}支{p['zhi']}藏{g}({w})")
    dedi = min(1.0, sum(
        w for p in pillars for g, w in HIDE_GAN[p["zhi"]] if GAN_WUXING[g] == dw))

    helper = wuxing[dw] + wuxing[[k for k, v in SHENG.items() if v == dw][0]]
    deshi = helper / total

    ratio = round(0.40 * deling + 0.25 * dedi + 0.35 * deshi, 4)
    if ratio >= 0.45:
        label = "身强"
    elif ratio >= 0.34:
        label = "中和偏强"
    elif ratio >= 0.24:
        label = "中和偏弱"
    else:
        label = "身弱"
    extreme = ratio >= 0.70 or ratio <= 0.10
    return {
        "ratio": ratio, "label": label,
        "deling": deling_txt, "deling_score": deling,
        "dedi_score": round(dedi, 3), "roots": roots,
        "deshi_score": round(deshi, 3),
        "cong_candidate": extreme,
        "note": "极端值，从格候选，需人工复核" if extreme else "",
    }


def pick_yongshen(day_gan, month_zhi, wuxing, strength):
    """Priority: 调候 -> 扶抑. Returns favour/avoid element sets plus reasoning."""
    dw = GAN_WUXING[day_gan]
    total = sum(wuxing.values()) or 1.0
    fire = wuxing["火"] / total
    water = wuxing["水"] / total

    if month_zhi in WINTER_ZHI and fire < 0.15:
        return {
            "method": "调候",
            "favor": ["火", "木"], "avoid": ["水", "金"],
            "reason": f"生于{month_zhi}月，命局寒湿而火仅占 {fire:.0%}，"
                      f"《穷通宝鉴》调候法先取火暖局，木以生火为辅。",
            "provenance": "rule:tiaohou",
        }
    if month_zhi in SUMMER_ZHI and water < 0.15:
        return {
            "method": "调候",
            "favor": ["水", "金"], "avoid": ["火", "土"],
            "reason": f"生于{month_zhi}月，命局燥烈而水仅占 {water:.0%}，"
                      f"调候法先取水润局，金以生水为辅。",
            "provenance": "rule:tiaohou",
        }

    sheng_me = [k for k, v in SHENG.items() if v == dw][0]
    i_sheng = SHENG[dw]
    i_ke = KE[dw]
    ke_me = [k for k, v in KE.items() if v == dw][0]

    if strength["label"] in ("身强", "中和偏强"):
        return {
            "method": "扶抑",
            "favor": [i_ke, i_sheng, ke_me], "avoid": [dw, sheng_me],
            "reason": f"日主{day_gan}({dw}) 判为{strength['label']}"
                      f"（旺度 {strength['ratio']:.2f}），宜克泄耗："
                      f"取{i_ke}(财)、{i_sheng}(食伤)、{ke_me}(官杀)。",
            "provenance": "rule:fuyi",
        }
    return {
        "method": "扶抑",
        "favor": [sheng_me, dw], "avoid": [i_ke, ke_me, i_sheng],
        "reason": f"日主{day_gan}({dw}) 判为{strength['label']}"
                  f"（旺度 {strength['ratio']:.2f}），宜生扶："
                  f"取{sheng_me}(印)、{dw}(比劫)。",
        "provenance": "rule:fuyi",
    }


def judge_geju(day_gan, month_zhi, pillars):
    """Month-command pattern. Transparent about which branch of the rule fired."""
    main_hidden = HIDE_GAN[month_zhi][0][0]
    transparent = None
    for p in pillars:
        if p["pos"] == "日":
            continue
        for g, _ in HIDE_GAN[month_zhi]:
            if p["gan"] == g:
                transparent = g
                break
        if transparent:
            break

    taken = transparent or main_hidden
    god = ten_god(day_gan, taken)
    name_map = {
        "正官": "正官格", "七杀": "七杀格", "正印": "正印格", "偏印": "偏印格",
        "食神": "食神格", "伤官": "伤官格", "正财": "正财格", "偏财": "偏财格",
        "比肩": "建禄格", "劫财": "月劫格",
    }
    all_gods = {p["shishen_gan"] for p in pillars if p["pos"] != "日"}
    broken, reason = None, []
    if god in ("正官",) and "伤官" in all_gods:
        broken, r = "破格", "伤官见官"
        reason.append(r)
    if god in ("正官", "七杀") and {"正官", "七杀"} <= all_gods:
        broken = broken or "破格"
        reason.append("官杀混杂")
    if god in ("正印", "偏印") and ("正财" in all_gods or "偏财" in all_gods):
        broken = broken or "破格"
        reason.append("财星坏印")
    if god == "食神" and "偏印" in all_gods:
        broken = broken or "破格"
        reason.append("枭神夺食")
    if god in ("正财", "偏财") and ("比肩" in all_gods or "劫财" in all_gods):
        broken = broken or "破格"
        reason.append("比劫夺财")

    return {
        "name": name_map.get(god, f"{god}格"),
        "taken_from": taken,
        "透干" if transparent else "月令本气": taken,
        "status": broken or "成格",
        "reason": "；".join(reason) if reason else "月令用神未见明显破坏",
        "provenance": "rule:geju-yueling",
    }


def find_relations(pillars):
    zs = [(p["pos"], p["zhi"]) for p in pillars]
    gs = [(p["pos"], p["gan"]) for p in pillars]
    out = {"gan_he": [], "zhi_he": [], "zhi_chong": [], "zhi_xing": [],
           "zhi_hai": [], "san_he": [], "san_hui": [], "chong_zhi": []}

    for i in range(len(gs)):
        for j in range(i + 1, len(gs)):
            pair = (gs[i][1], gs[j][1])
            for k, elem in GAN_HE.items():
                if set(pair) == set(k):
                    out["gan_he"].append(
                        {"pos": f"{gs[i][0]}{gs[j][0]}", "pair": "".join(pair),
                         "hua": elem})
    for i in range(len(zs)):
        for j in range(i + 1, len(zs)):
            a, b = zs[i][1], zs[j][1]
            tag = f"{zs[i][0]}{zs[j][0]}"
            for k, elem in ZHI_HE.items():
                if {a, b} == set(k):
                    out["zhi_he"].append({"pos": tag, "pair": a + b, "hua": elem})
            for k in ZHI_CHONG:
                if {a, b} == set(k):
                    out["zhi_chong"].append({"pos": tag, "pair": a + b})
                    out["chong_zhi"] += [a, b]
            for k, nm in XING_PAIRS:
                if {a, b} == set(k):
                    out["zhi_xing"].append({"pos": tag, "pair": a + b, "type": nm})
            for k in ZHI_HAI:
                if {a, b} == set(k):
                    out["zhi_hai"].append({"pos": tag, "pair": a + b})
            if a == b and a in SELF_XING:
                out["zhi_xing"].append({"pos": tag, "pair": a + b, "type": "自刑"})

    zset = [z for _, z in zs]
    for trio, nm in XING_GROUPS:
        if all(t in zset for t in trio):
            out["zhi_xing"].append({"pos": "全局", "pair": "".join(trio), "type": nm})
    for trio, elem in SAN_HE.items():
        hit = [t for t in trio if t in zset]
        if len(hit) == 3:
            out["san_he"].append({"pair": "".join(trio), "hua": elem, "full": True})
        elif len(hit) == 2 and trio[1] in hit:
            out["san_he"].append({"pair": "".join(hit), "hua": elem, "full": False})
    for trio, elem in SAN_HUI.items():
        if all(t in zset for t in trio):
            out["san_hui"].append({"pair": "".join(trio), "hua": elem})
    out["chong_zhi"] = sorted(set(out["chong_zhi"]))
    return out


def find_shensha(day_gan, year_zhi, day_zhi, pillars, xunkong):
    zs = {p["pos"]: p["zhi"] for p in pillars}
    hits = []

    def add(name, where, note):
        hits.append({"name": name, "at": where, "note": note})

    for pos, z in zs.items():
        if z in TIANYI.get(day_gan, ""):
            add("天乙贵人", pos, "遇难有人扶，逢凶化吉的结构性缓冲")
        if z == WENCHANG[day_gan]:
            add("文昌", pos, "读书、考试、文字表达之利")
        if z == YANGREN[day_gan]:
            add("羊刃", pos, "刚烈果决，成败俱大，需有官杀制之")
        if z == JINYU[day_gan]:
            add("金舆", pos, "得配偶或物质之助")

    for base_name, base in (("年支", year_zhi), ("日支", day_zhi)):
        trio = TRIAD_OF.get(base)
        if not trio:
            continue
        for pos, z in zs.items():
            if z == TAOHUA[trio]:
                add("桃花", pos, f"以{base_name}起，主人缘、异性缘、才艺")
            if z == YIMA[trio]:
                add("驿马", pos, f"以{base_name}起，主迁移、外出、变动")
            if z == HUAGAI[trio]:
                add("华盖", pos, f"以{base_name}起，主孤高、玄学、专业深度")

    day_pillar = zs.get("日")
    dg = [p for p in pillars if p["pos"] == "日"][0]
    if dg["gan"] + dg["zhi"] in KUIGANG:
        add("魁罡", "日柱", "性格刚断，宜身强，忌刑冲")

    for grp, (gu, gua) in GUCHEN_GUASU.items():
        if year_zhi in grp:
            for pos, z in zs.items():
                if z == gu:
                    add("孤辰", pos, "主孤独感，六亲缘薄")
                if z == gua:
                    add("寡宿", pos, "主孤独感，六亲缘薄")

    for pos, z in zs.items():
        if z in xunkong:
            add("空亡", pos, "该柱所主之事易落空、需重来，非必凶")
    return hits


# ---------------------------------------------------------------- ziwei

def time_index_of(dt: datetime) -> int:
    h = dt.hour
    if h == 23:
        return 12          # 晚子时
    return (h + 1) // 2


def build_ziwei(dt: datetime, gender: str):
    ti = time_index_of(dt)
    a = iztro_py.by_solar(dt.strftime("%Y-%m-%d"), ti, gender)
    palaces = []
    for p in a.palaces:
        palaces.append({
            "index": p.index,
            "name": zw_name(p.name, "palace"),
            "gan": zw_name(p.heavenly_stem, "stem"),
            "zhi": zw_name(p.earthly_branch, "branch"),
            "is_body": p.is_body_palace,
            "major_stars": [{"name": zw_name(s.name, "star"),
                             "brightness": s.brightness,
                             "mutagen": s.mutagen} for s in p.major_stars],
            "minor_stars": [{"name": zw_name(s.name, "star"),
                             "mutagen": s.mutagen} for s in p.minor_stars],
            "adjective_stars": [zw_name(s.name, "star") for s in p.adjective_stars],
            "changsheng12": p.changsheng12,
            "decadal_range": list(p.decadal.range) if p.decadal else None,
            "decadal_ganzhi": (zw_name(p.decadal.heavenly_stem, "stem")
                               + zw_name(p.decadal.earthly_branch, "branch"))
            if p.decadal else None,
        })
    birth_mutagen = {}
    for p in palaces:
        for s in p["major_stars"] + p["minor_stars"]:
            if s.get("mutagen"):
                birth_mutagen[s["mutagen"]] = {"star": s["name"], "palace": p["name"]}
    return {
        "time_index": ti,
        "wuxingju": a.five_elements_class,
        "soul_star": zw_name(a.soul, "star"),
        "body_star": zw_name(a.body, "star"),
        "soul_palace_zhi": zw_name(a.earthly_branch_of_soul_palace, "branch"),
        "body_palace_zhi": zw_name(a.earthly_branch_of_body_palace, "branch"),
        "zodiac": a.zodiac,
        "sign": a.sign,
        "chinese_date": a.chinese_date,
        "lunar_date": a.lunar_date,
        "palaces": palaces,
        "birth_mutagen": birth_mutagen,
    }, a


# ---------------------------------------------------------------- main build

def build(args):
    if args.lunar:
        y, m, d = [int(x) for x in args.lunar.split("-")]
        hh, mm = [int(x) for x in args.time.split(":")]
        base_solar = Lunar.fromYmdHms(y, m, d, hh, mm, 0).getSolar()
        clock = datetime(base_solar.getYear(), base_solar.getMonth(),
                         base_solar.getDay(), hh, mm)
    else:
        y, m, d = [int(x) for x in args.solar.split("-")]
        hh, mm = [int(x) for x in args.time.split(":")]
        clock = datetime(y, m, d, hh, mm)

    lon = args.lon
    if lon is None and args.city:
        lon = CITY_LON.get(args.city.replace("市", "").replace("省", ""))
    tst_applied = lon is not None and not args.no_tst
    if tst_applied:
        eff, lon_min, eot_min = apply_true_solar_time(clock, lon, not args.no_eot)
    else:
        eff, lon_min, eot_min = clock, 0.0, 0.0

    boundary_flip = shichen_of(eff) != shichen_of(clock)

    solar = Solar.fromYmdHms(eff.year, eff.month, eff.day, eff.hour, eff.minute, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    ec.setSect(args.sect)

    # 23:00-24:00 is where the two schools split, and they disagree on the DAY
    # MASTER itself — everything downstream flips. Never let this pass silently.
    late_zi = eff.hour == 23
    alt_pillars = None
    if late_zi:
        alt = Solar.fromYmdHms(eff.year, eff.month, eff.day,
                               eff.hour, eff.minute, 0).getLunar().getEightChar()
        alt.setSect(1 if args.sect == 2 else 2)
        alt_pillars = {"sect": 1 if args.sect == 2 else 2,
                       "pillars": [alt.getYear(), alt.getMonth(),
                                   alt.getDay(), alt.getTime()],
                       "day_master": alt.getDayGan()}

    raw = [("年", ec.getYear()), ("月", ec.getMonth()),
           ("日", ec.getDay()), ("时", ec.getTime())]
    day_gan = ec.getDayGan()
    pillars = []
    for pos, gz in raw:
        g, z = gz[0], gz[1]
        pillars.append({
            "pos": pos, "gan": g, "zhi": z, "ganzhi": gz,
            "gan_wuxing": GAN_WUXING[g], "zhi_wuxing": ZHI_WUXING[z],
            "shishen_gan": "日主" if pos == "日" else ten_god(day_gan, g),
            "hide_gan": [{"gan": hg, "weight": w, "shishen": ten_god(day_gan, hg)}
                         for hg, w in HIDE_GAN[z]],
        })
    for p, getter in zip(pillars, [ec.getYearNaYin, ec.getMonthNaYin,
                                   ec.getDayNaYin, ec.getTimeNaYin]):
        p["nayin"] = getter()
    for p, getter in zip(pillars, [ec.getYearDiShi, ec.getMonthDiShi,
                                   ec.getDayDiShi, ec.getTimeDiShi]):
        p["dishi"] = getter()

    month_zhi, day_zhi, year_zhi = pillars[1]["zhi"], pillars[2]["zhi"], pillars[0]["zhi"]
    relations = find_relations(pillars)
    wuxing, wx_detail = score_wuxing(pillars, month_zhi, day_zhi, relations["chong_zhi"])
    strength = judge_strength(day_gan, month_zhi, day_zhi, pillars, wuxing,
                              relations["chong_zhi"])
    yongshen = pick_yongshen(day_gan, month_zhi, wuxing, strength)
    geju = judge_geju(day_gan, month_zhi, pillars)
    xunkong = ec.getDayXunKong()
    shensha = find_shensha(day_gan, year_zhi, day_zhi, pillars, xunkong)

    gender_num = 1 if args.gender in ("男", "male", "m", "M") else 0
    gender_cn = "男" if gender_num else "女"
    yun = ec.getYun(gender_num)
    dayun = []
    for dy in yun.getDaYun():
        gz = dy.getGanZhi()
        dayun.append({
            "index": dy.getIndex(),
            "ganzhi": gz or "(起运前)",
            "gan": gz[0] if gz else None,
            "zhi": gz[1] if gz else None,
            "start_age": dy.getStartAge(), "end_age": dy.getEndAge(),
            "start_year": dy.getStartYear(), "end_year": dy.getEndYear(),
            "shishen_gan": ten_god(day_gan, gz[0]) if gz else None,
            "wuxing_gan": GAN_WUXING[gz[0]] if gz else None,
            "wuxing_zhi": ZHI_WUXING[gz[1]] if gz else None,
        })

    ziwei, _astro = build_ziwei(eff, gender_cn)

    return {
        "meta": {
            "generated_by": "mingtu/paipan.py",
            "name": args.name,
            "gender": gender_cn,
            "clock_time": clock.strftime("%Y-%m-%d %H:%M"),
            "effective_time": eff.strftime("%Y-%m-%d %H:%M"),
            "city": args.city, "longitude": lon,
            "true_solar_time_applied": tst_applied,
            "longitude_correction_min": round(lon_min, 1),
            "equation_of_time_min": round(eot_min, 1),
            "shichen_clock": shichen_of(clock),
            "shichen_effective": shichen_of(eff),
            "shichen_boundary_flip": boundary_flip,
            "hour_known": not args.hour_unknown,
            "sect": args.sect,
            "sect_name": "晚子时法（日柱仍属当日，时柱以次日干起）" if args.sect == 2
            else "早子时法（23 时后日柱即算次日）",
            "late_zi": late_zi,
            "sect_alternative": alt_pillars,
            "lunar": lunar.toString(),
            "jieqi_prev": lunar.getPrevJieQi().getName(),
            "confidence_note": (
                "真太阳时校正后时辰发生跳变，两个时辰的盘都应参考" if boundary_flip
                else "时辰稳定"),
        },
        "bazi": {
            "pillars": pillars,
            "day_master": {
                "gan": day_gan, "wuxing": GAN_WUXING[day_gan],
                "yinyang": "阳" if GAN_YINYANG[day_gan] > 0 else "阴",
            },
            "xunkong": xunkong,
            "wuxing_score": wuxing,
            "wuxing_detail": wx_detail,
            "strength": strength,
            "yongshen": yongshen,
            "geju": geju,
            "relations": relations,
            "shensha": shensha,
            "taiyuan": ec.getTaiYuan(), "minggong": ec.getMingGong(),
            "shengong": ec.getShenGong(),
        },
        "dayun": {
            "direction": "顺行" if yun.getDaYun()[1].getGanZhi() and
            GAN.index(yun.getDaYun()[1].getGanZhi()[0]) ==
            (GAN.index(pillars[1]["gan"]) + 1) % 10 else "逆行",
            "start_after": f"{yun.getStartYear()}年{yun.getStartMonth()}个月{yun.getStartDay()}天",
            "start_solar": yun.getStartSolar().toYmd(),
            "steps": dayun,
        },
        "ziwei": ziwei,
    }


def print_summary(chart, out_path=None):
    m, b = chart["meta"], chart["bazi"]
    if out_path:
        print(f"✓ {out_path}")
    print(f"  四柱 {' '.join(p['ganzhi'] for p in b['pillars'])}"
          f"  日主 {b['day_master']['gan']}({b['day_master']['wuxing']})"
          f"  {b['strength']['label']}  {b['geju']['name']}·{b['geju']['status']}")
    print(f"  用神 {'/'.join(b['yongshen']['favor'])}"
          f"  忌 {'/'.join(b['yongshen']['avoid'])}"
          f"  [{b['yongshen']['method']}]")
    if m["shichen_boundary_flip"]:
        print(f"  ⚠ 真太阳时使时辰由 {m['shichen_clock']} 变为 "
              f"{m['shichen_effective']}，两盘都要看")
    if m["late_zi"]:
        alt = m["sect_alternative"]
        print(f"  ⚠ 生于晚子时。当前用{m['sect_name']}；"
              f"另一流派作 {' '.join(alt['pillars'])}，日主为 {alt['day_master']}。"
              f"日主不同则全盘不同，必须向命主说明口径")
