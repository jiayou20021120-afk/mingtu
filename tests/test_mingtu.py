"""Regression tests. The point of these is not coverage — it is that the four
deterministic layers stay deterministic. If a scoring weight is retuned, the
snapshot tests below should fail loudly, not drift silently.
"""
import json
from datetime import date
from types import SimpleNamespace

import pytest

from mingtu import build_chart, build_lifeline, build_yunshi, build_html
from mingtu.lifeline import DIM_TOTAL, DIMS, _confidence, turning_weight
from mingtu.chart import ten_god, equation_of_time, GAN, ZHI, HIDE_GAN


def args(**kw):
    base = dict(solar="2000-8-16", lunar=None, time="03:30", gender="男",
                name="测试", city="北京", lon=None, no_tst=False, no_eot=False,
                hour_unknown=False, sect=2)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture(scope="module")
def chart():
    return build_chart(args())


@pytest.fixture(scope="module")
def life(chart):
    return build_lifeline(chart, 90, "男")


# ------------------------------------------------------------------ calendar

def test_four_pillars_known_case(chart):
    got = [p["ganzhi"] for p in chart["bazi"]["pillars"]]
    assert got == ["庚辰", "甲申", "丙午", "庚寅"]
    assert chart["bazi"]["day_master"]["gan"] == "丙"


def test_true_solar_time_shifts_clock(chart):
    m = chart["meta"]
    assert m["true_solar_time_applied"]
    assert m["longitude_correction_min"] == pytest.approx(-14.4, abs=0.1)
    assert m["effective_time"] != m["clock_time"]


def test_longitude_can_cross_a_shichen_boundary():
    """Urumqi is ~32 degrees west of the Beijing meridian; that is over two
    hours, which is more than one 时辰. Silently ignoring it is a real error."""
    c = build_chart(args(solar="1988-2-4", time="07:10", gender="女",
                         city="乌鲁木齐"))
    assert c["meta"]["shichen_boundary_flip"] is True
    assert c["meta"]["shichen_clock"] == "辰"
    assert c["meta"]["shichen_effective"] == "寅"


def test_equation_of_time_bounds():
    vals = [equation_of_time(date(2024, m, 15)) for m in range(1, 13)]
    assert all(-17 < v < 17 for v in vals)


# ------------------------------------------------------------------ late zi

def test_late_zi_reports_the_other_school():
    """23:00-24:00 is where the two schools disagree about the DAY MASTER.
    Both must be surfaced; picking one silently would be the worst kind of bug."""
    a = build_chart(args(solar="1988-2-4", time="23:40", gender="男",
                         city=None, sect=2))
    b = build_chart(args(solar="1988-2-4", time="23:40", gender="男",
                         city=None, sect=1))
    assert a["meta"]["late_zi"] and b["meta"]["late_zi"]
    assert a["bazi"]["day_master"]["gan"] == "己"
    assert b["bazi"]["day_master"]["gan"] == "庚"
    assert a["meta"]["sect_alternative"]["day_master"] == "庚"
    assert b["meta"]["sect_alternative"]["day_master"] == "己"


def test_non_late_zi_has_no_sect_warning(chart):
    assert chart["meta"]["late_zi"] is False
    assert chart["meta"]["sect_alternative"] is None


# ------------------------------------------------------------------ rules

@pytest.mark.parametrize("day,other,expect", [
    ("丙", "庚", "偏财"), ("丙", "辛", "正财"), ("丙", "壬", "七杀"),
    ("丙", "癸", "正官"), ("丙", "甲", "偏印"), ("丙", "乙", "正印"),
    ("丙", "丙", "比肩"), ("丙", "丁", "劫财"), ("丙", "戊", "食神"),
    ("丙", "己", "伤官"),
])
def test_ten_gods_complete_for_one_day_master(day, other, expect):
    assert ten_god(day, other) == expect


def test_hidden_stem_weights_sum_sanely():
    for z, parts in HIDE_GAN.items():
        total = sum(w for _, w in parts)
        assert 0.6 <= total <= 1.0, z


def test_yongshen_has_no_overlap(chart):
    y = chart["bazi"]["yongshen"]
    assert not (set(y["favor"]) & set(y["avoid"]))
    assert y["method"] in ("调候", "扶抑")
    assert y["reason"]


def test_winter_chart_takes_tiaohou():
    """Born deep in winter with almost no fire: the climate rule must win over
    the plain strong/weak rule, else the whole life arc inverts."""
    c = build_chart(args(solar="1990-12-25", time="02:00", gender="男",
                         city="哈尔滨"))
    if c["bazi"]["yongshen"]["method"] == "调候":
        assert "火" in c["bazi"]["yongshen"]["favor"]


def test_dayun_direction_and_count(chart):
    steps = chart["dayun"]["steps"]
    assert len(steps) >= 9
    real = [s for s in steps if s["gan"]]
    for a, b in zip(real, real[1:]):
        assert b["start_age"] == a["end_age"] + 1
        assert b["end_age"] - b["start_age"] == 9


# ------------------------------------------------------------------ lifeline

def test_dimension_normalisers_are_positive():
    for gender in ("男", "女"):
        for d in DIMS:
            assert DIM_TOTAL[gender][d] > 0


def test_lifeline_covers_every_year(life):
    assert len(life["years"]) == 91
    assert [r["age"] for r in life["years"]] == list(range(91))
    for r in life["years"]:
        assert set(r["dims"]) == set(DIMS)


def test_cycles_are_ranked_without_ties_in_position(life):
    scored = [c for c in life["cycles"] if c["ganzhi"] != "(起运前)"]
    ranks = sorted(c["rank"] for c in scored)
    assert ranks == list(range(1, len(scored) + 1))
    assert all(0.0 <= c["relative"] <= 1.0 for c in scored)


def test_turning_points_are_selective(life):
    """A list flagging 60% of years as pivotal flags nothing at all."""
    tp = life["overview"]["turning_points"]
    assert len(tp) <= 15
    assert len(tp) < len(life["years"]) * 0.25
    assert all(t["weight"] >= 3 for t in tp)


def test_both_systems_actually_contribute(life):
    """If one side were dead, every ziwei_dims would be zero and the whole
    cross-check would be theatre."""
    nonzero_bazi = sum(1 for r in life["years"] if any(r["bazi_dims"].values()))
    nonzero_ziwei = sum(1 for r in life["years"] if any(r["ziwei_dims"].values()))
    assert nonzero_bazi > 60
    assert nonzero_ziwei > 60


def test_disagreement_is_recorded_not_smoothed(life):
    """Two independent systems must sometimes disagree. If they never did, the
    scoring would be double-counting one signal."""
    kinds = {v for r in life["years"] for v in r["agreement"].values()}
    assert "共振" in kinds and "冲突" in kinds
    assert any(r["confidence"] in ("低", "分歧") for r in life["years"])


def test_confidence_requires_agreement_not_just_volume():
    assert _confidence(dict.fromkeys(DIMS, "共振")) == "高"
    assert _confidence(dict.fromkeys(DIMS, "冲突")) == "低"
    half = {"事业": "共振", "财富": "共振", "婚恋": "共振",
            "健康": "冲突", "学业": "冲突", "人际": "冲突"}
    assert _confidence(half) == "分歧"


def test_turning_weight_favours_heavy_tags():
    heavy = [{"tag": "岁运并临", "level": "major"}]
    light = [{"tag": "冲提纲", "level": "major"}]
    assert turning_weight(heavy) > turning_weight(light)


# ------------------------------------------------------------------ yunshi

def test_scope_weights_are_ordered():
    c = build_chart(args())
    r = build_yunshi(c, date(2026, 8, 9), 3)
    assert r["year"]["weight"] > r["month"]["weight"] > r["day"]["weight"]
    assert len(r["upcoming"]) == 2
    assert set(r["stacked"]["dims"]) == set(DIMS)


# ------------------------------------------------------------------ render

def test_html_is_self_contained(chart, life):
    html = build_html(chart, life, 2018, 2030)
    assert html.startswith("<!doctype html>")
    for bad in ("<script", "http://", "https://cdn", "src=\"http"):
        assert bad not in html.lower()
    assert "prefers-color-scheme" in html
    assert "不构成医疗" in html


# ------------------------------------------------------------------ profile

def test_profile_roundtrip_and_suggestions(tmp_path, monkeypatch):
    monkeypatch.setenv("MINGTU_HOME", str(tmp_path))
    from mingtu import profile as P
    prof = P.create("张三", solar="1995-3-12", time="14:20", gender="男")
    for i in range(3):
        P.add_calibration(prof, 2010 + i, "婚恋高点", "无事发生", "落空", "婚恋")
    P.save(prof)
    again = P.load(prof["slug"])
    assert again["summary"]["n"] == 3
    assert again["summary"]["hit_rate"] == 0.0
    assert any("婚恋" in a for a in again["adjustments"])


# ------------------------------------------------------------------ packaging

def test_sources_parse_under_older_grammars():
    """Developing on 3.14 hides constructs that 3.9-3.11 reject — PEP 701
    f-strings being the one that actually bit. Parse every module against the
    oldest grammar we claim to support."""
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    files = sorted((root / "src" / "mingtu").glob("*.py"))
    assert files, "no sources found"
    for p in files:
        src = p.read_text(encoding="utf-8")
        for minor in (9, 11):
            ast.parse(src, filename=str(p), feature_version=(3, minor))


def test_cli_exposes_every_documented_subcommand():
    from mingtu.cli import build_parser
    ap = build_parser()
    actions = [a for a in ap._subparsers._group_actions if a.choices]
    names = set(actions[0].choices)
    assert {"full", "chart", "life", "day", "hour",
            "render", "profile"} <= names
