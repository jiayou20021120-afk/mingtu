# 命途 mingtu

**八字与紫微斗数双轴人生全流程推演。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![Agent Skills](https://img.shields.io/badge/SKILL.md-compatible-c1432f)](https://code.claude.com/docs/en/skills)

简体中文 · [English](README.en.md)

现有的命理工具给的是**快照**：本命盘、当前大运、未来一两年。
命途给的是**形状**：出生到九十岁的完整曲线，八字与紫微各自独立推一遍，
逐年交叉对账，哪里一致、哪里打架、哪里是转折，全部标出来。

命令行能用，也能作为 SKILL.md 装进任何支持该标准的 AI agent。

---

## 装

```bash
pip install mingtu
```

从源码装，并顺带把 skill 包装进你已有的 AI agent：

```bash
git clone https://github.com/jiayou20021120-afk/mingtu.git
cd mingtu && ./install.sh
```

---

## 用

### 不想碰命令行：开网页

```bash
mingtu serve
```

浏览器自动打开一个表单，填生辰点排盘就出结果。服务只绑 `127.0.0.1`，
生辰数据全程不出这台机器——没有上传、没有统计、没有任何对外请求。
不知道时辰的话，表单里勾上「我不知道出生时辰」，按提示写几件已发生的事就能反推。

### 命令行

一条命令跑完整个管线：

```bash
mingtu full --solar 1995-3-12 --time 14:20 --gender 女 --city 杭州 --name 张三 --today
```

```
✓ chart.json
  四柱 乙亥 己卯 壬寅 丁未  日主 壬(水)  中和偏强  伤官格·成格
  用神 火/木/土  忌 水/金  [扶抑]

✓ lifeline.json  91 年 / 10 步大运
   9-18岁 庚辰(偏印) +0.10 #9/9 █            强:婚恋 弱:学业
  19-28岁 辛巳(正印) +0.23 #6/9 ████         强:婚恋 弱:学业
  29-38岁 壬午(比肩) +0.15 #7/9 █            强:财富 弱:人际
  39-48岁 癸未(劫财) +0.51 #3/9 ███████████  强:婚恋 弱:健康
  49-58岁 甲申(食神) +0.52 #2/9 ████████████ 强:婚恋 弱:事业
  ...
  关键转折 12 处：2028, 2004, 2064, 2001, 2005, 2014, 2024, 2033

✓ 张三-命途.html
```

分步：

```bash
mingtu serve                                        # 网页界面
mingtu chart  --solar 1995-3-12 --time 14:20 --gender 女 --city 杭州
mingtu life   --chart chart.json --to-age 90
mingtu day    --chart chart.json --span 7          # 流年 / 流月 / 流日
mingtu render --chart chart.json --lifeline lifeline.json --out 命途.html
mingtu hour   --solar 1995-3-12 --gender 女 --events events.json
mingtu profile list
```

也可以当库用：

```python
from types import SimpleNamespace
from mingtu import build_chart, build_lifeline, build_html

chart = build_chart(SimpleNamespace(
    solar="1995-3-12", lunar=None, time="14:20", gender="女",
    name="张三", city="杭州", lon=None,
    no_tst=False, no_eot=False, hour_unknown=False, sect=2))

life = build_lifeline(chart, to_age=90, gender="女")
print(life["overview"]["golden_cycles"])
open("out.html", "w").write(build_html(chart, life))
```

---

## 它做什么

### 两条时间轴叠在一起

八字大运和紫微大限是两套刻度完全不同的时间轴：起运岁数算法不同、排列方向规则不同、
换轨点几乎从不重合。命途把它们叠到同一条 0–90 岁网格上逐年对账：

- 两条轴都说"这十年主事业" → **共振**，置信度高
- 一条进一条退 → **冲突**，如实标注两套读法相反
- 换轨点相隔两三年 → 那几年是**过渡带**

实测下来，全生命周期通常只有两三成年份两套体系强一致。
**这个数字本身就是信息，合并掩盖才是欺骗。**

### 六个维度逐年打分

事业 · 财富 · 婚恋 · 健康 · 学业 · 人际。
八字侧走"流年十神 × 用神极性"，紫微侧走"流年四化飞入哪个流年宫"，两侧独立计算再对账。

### 关键转折按叠加判定

换运、岁运并临、伏吟、反吟、冲提纲、冲日支、空亡、化忌入命/夫妻/疾厄……
单项信号不算转折——冲提纲每十二年来一次。只有权重叠加到阈值才收进 `turning_points`，
且最多十五个。九十年里标出五十个"关键年份"，等于一个都没标。

### 时辰未知就反推，反推不出就说不出

十二时辰各排一套盘，用已发生的人生事件打分排名。区分度不够时判 **"不可用"**，
不挑第一名假装知道。

### 校准会留下来

`~/.mingtu/profiles/` 存档命中与落空，自动算命中率、按维度归因，
某维度连续落空三次时提出调整建议。同一个人下次再来，先读档案。

---

## 四层架构

```
L0  历法   lunar-python + iztro-py    四柱、节气、大运、十二宫、四化
L1  规则   硬编码                      旺衰、用神、格局、刑冲合害、神煞
L2  时间轴 硬编码                      六维逐年打分、双系统对账、事件判定
L3  叙事   留给读者（人或 LLM）         skill/references/ 里是写作纪律
```

**前三层没有一个字是生成的。** 纯 LLM 排盘会错排日柱，日柱错则日主错、格局错、用神错，
后面九十年全是反的——这是所有同类项目的共识，也是这套东西把 L0–L2 全部锁进确定性代码的原因。

---

## 几个刻意的设计取舍

**绝对分不跨人比。** 用神占三个五行的命，一辈子的分都偏正。
所以真正有意义的是 `cycles[].rank`（这步在本人十步大运里排第几）
和 `years[].percentile_in_life`。判词一律用相对表述。

**六维按总喂入量归一化。** 不归一化的话，喂入源最多、基础分最高的那个维度会在
每一步大运都夺冠，六个维度等于一个。

**口径先声明。** 子时换日、真太阳时、立春换年、节气换月、紫微流派，每一项都会改变盘面。
晚子时（23:00–24:00）的两派**给出不同的日主**——不是细节差异，是全盘换人。
命途会同时输出另一派的四柱并强制警告。

**一天不决定什么。** 流年 1.0 / 流月 0.55 / 流日 0.3。
好流日落在坏流年里永远读不成行动信号。

---

## 目录

```
src/mingtu/
  chart.py      L0+L1 排盘
  lifeline.py   L2 人生时间轴
  yunshi.py     流年/流月/流日
  hour.py       时辰反推
  render.py     单文件 HTML 人生长卷
  serve.py      本地网页界面（只绑 127.0.0.1）
  profile.py    校准档案
  cli.py        统一入口
skill/
  SKILL.md      给 AI agent 的入口：铁律、工作流、失败处理
  references/   干支表、旺衰格局、紫微星曜、时间轴规则、叙事纪律、校准协议
tests/          37 项回归测试，锁住确定性层不漂移
```

---

## 开发

```bash
git clone https://github.com/jiayou20021120-afk/mingtu.git
cd mingtu
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m pytest -q
```

---

## 致谢

- [lunar-python](https://github.com/6tail/lunar-python)（6tail）— 历法、四柱、大运、神煞
- [iztro](https://github.com/SylarLong/iztro) / iztro-py（SylarLong）— 紫微斗数排盘与流曜

两库对四柱的计算互为交叉验证。

---

## 免责

仅供传统文化研究与自我参照，不构成医疗、投资、婚姻、法律等任何决策依据。
命盘描述的是结构性倾向，不是概率，更不是事实。

不算生死，不推寿元。

MIT License.
