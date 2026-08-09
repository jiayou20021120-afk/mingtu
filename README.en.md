# mingtu 命途

**Chinese destiny analysis across a whole life arc — Bazi and Ziwei Doushu, cross-checked year by year.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)

[简体中文](README.md) · English

Existing tools give you a **snapshot**: the natal chart, the current luck cycle,
maybe the next year or two. mingtu gives you the **shape**: a full curve from
birth to ninety, computed independently by two systems and reconciled year by
year, with agreements, contradictions and turning points all marked.

Works as a CLI, and ships as a SKILL.md bundle for any agent that reads the standard.

---

## Install

```bash
pip install mingtu
```

From source, and optionally install the skill bundle into whichever AI agents you have:

```bash
git clone https://github.com/jiayou20021120-afk/mingtu.git
cd mingtu && ./install.sh
```

---

## Use

```bash
mingtu full --solar 1995-3-12 --time 14:20 --gender 女 --city 杭州 --today
```

Produces `chart.json`, `lifeline.json` and a self-contained HTML scroll.

```bash
mingtu chart  --solar 1995-3-12 --time 14:20 --gender 女 --city 杭州
mingtu life   --chart chart.json --to-age 90
mingtu day    --chart chart.json --span 7        # year / month / day fortune
mingtu render --chart chart.json --lifeline lifeline.json --out life.html
mingtu hour   --solar 1995-3-12 --gender 女 --events events.json
mingtu profile list
```

Gender takes `男` (male) or `女` (female); the branch-hour and palace vocabulary
is Chinese throughout, since the domain terms have no stable English equivalents.

---

## What it actually does

### Two timelines, laid over one another

A Bazi luck cycle and a Ziwei decade limit are two unrelated rulers. They start
at different ages (one from the distance to the nearest solar term, the other
from the Five-Element Bureau), they run in directions set by different rules,
and their boundaries almost never coincide. mingtu lays both on a single 0–90
grid and reconciles them annually:

- both axes point the same way → **resonance**, high confidence
- one says advance, the other retreat → **conflict**, reported as such
- boundaries two or three years apart → a **transition band**

In practice the two systems strongly agree on only 20–30% of years across a
lifetime. **That number is itself the finding.** Averaging it away would be a lie.

### Six dimensions, scored yearly

Career · Wealth · Marriage · Health · Study · Relationships.
The Bazi side scores from the year's ten-gods weighted by whether their element
is favourable for that chart. The Ziwei side scores from which palace each of
the year's four transformation stars flies into. Neither side sees the other.

### Turning points require stacking

A single structural signal is not a turning point — a month-branch clash recurs
every twelve years. Only weighted stacks above threshold enter `turning_points`,
capped at fifteen. Flagging fifty "pivotal years" out of ninety flags nothing.

### An unknown birth hour is recovered, or declared unrecoverable

All twelve hours are charted and scored against life events the person can
confirm. When the margin is too narrow the verdict is **"unusable"** and no
winner is picked. Guessing 子時 corrupts the day pillar, and with it the day
master, the pattern, the favourable elements and every year downstream.

### Calibration persists

`~/.mingtu/profiles/` records which predictions landed. It computes hit rate,
attributes misses by dimension, and proposes an adjustment when a dimension
misses three times running.

---

## Four layers

```
L0  calendar   lunar-python + iztro-py   pillars, solar terms, cycles, palaces
L1  rules      hard-coded                strength, favourable elements, patterns
L2  timeline   hard-coded                yearly six-dimension scoring, reconciliation
L3  narrative  left to the reader        writing discipline in skill/references/
```

**Nothing in L0–L2 is generated.** Every同类 project converges on the same
lesson: an LLM left to cast the chart itself gets the day pillar wrong, and one
wrong pillar inverts everything after it.

---

## Deliberate trade-offs

**Absolute scores don't compare across people.** A chart whose favourable set
covers three of the five elements runs positive its whole life. What matters is
`cycles[].rank` — where a cycle sits among that person's own ten — and
`years[].percentile_in_life`.

**Dimensions are normalised by total feed.** Without it, whichever dimension has
the most inputs wins every cycle and six dimensions collapse into one.

**Conventions are declared before conclusions.** Day boundary at midnight,
true solar time, year boundary at 立春, month boundary at solar terms, Ziwei
school. The two late-hour schools **produce different day masters** — mingtu
prints the other school's pillars and refuses to pass it silently.

**A day decides nothing.** Year 1.0 / month 0.55 / day 0.3. A good day inside a
hostile year never reads as a green light.

---

## Development

```bash
git clone https://github.com/jiayou20021120-afk/mingtu.git
cd mingtu
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m pytest -q
```

31 regression tests pin the deterministic layers so retuned weights fail loudly
rather than drifting.

---

## Credits

- [lunar-python](https://github.com/6tail/lunar-python) by 6tail — calendar, pillars, luck cycles
- [iztro](https://github.com/SylarLong/iztro) / iztro-py by SylarLong — Ziwei Doushu charting

The two libraries cross-validate each other on the four pillars.

---

## Disclaimer

For cultural study and personal reflection only. Not medical, financial, marital
or legal advice. A chart describes structural tendency — not probability, and
certainly not fact.

No lifespan prediction. Ever.

MIT License.
