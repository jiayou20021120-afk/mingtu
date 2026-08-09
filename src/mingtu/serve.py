"""A local web form, for people who do not want a terminal.

Binds to 127.0.0.1 only and holds nothing on disk unless you ask it to. Birth
data is the kind of thing that should not leave the machine it was typed on,
so there is no upload, no telemetry and no outbound request anywhere in here.
"""
import html
import json
import threading
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs

from .chart import CITY_LON, build as build_chart
from .lifeline import build as build_lifeline
from .render import CSS, build_html
from .yunshi import build as build_yunshi
from .hour import rank as rank_hours, classify

FORM_CSS = CSS + """
form{max-width:760px}
fieldset{border:1px solid #e0d9cc;border-radius:3px;padding:20px 22px;margin:0 0 20px}
legend{font-size:11px;letter-spacing:.2em;color:#a1968a;padding:0 8px}
label{display:block;font-size:12px;letter-spacing:.1em;color:#7d7364;margin:0 0 5px}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px}
input[type=text],input[type=date],input[type=time],select,textarea{
 width:100%;padding:9px 11px;border:1px solid #d8cfbe;border-radius:3px;
 background:#fff;color:inherit;font:15px/1.5 inherit}
textarea{min-height:112px;font-size:13.5px;resize:vertical}
input:focus,select:focus,textarea:focus{outline:2px solid #c9bda8;outline-offset:-1px}
.hint{font-size:12px;color:#9b9184;margin:6px 0 0;line-height:1.65}
.seg{display:flex;gap:0}
.seg label{flex:1;margin:0;text-align:center;padding:9px 0;border:1px solid #d8cfbe;
 cursor:pointer;font-size:15px;letter-spacing:.1em;color:inherit;background:#fff}
.seg label:first-of-type{border-radius:3px 0 0 3px}
.seg label:last-of-type{border-radius:0 3px 3px 0;border-left:0}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg input:checked+span{font-weight:600}
.seg label:has(input:checked){background:#efe8db;border-color:#bdb09a}
button{background:#232025;color:#faf8f4;border:0;border-radius:3px;
 padding:13px 30px;font:15px/1 inherit;letter-spacing:.14em;cursor:pointer}
button:hover{background:#3a353f}
.ghost{background:transparent;color:#7d7364;border:1px solid #d8cfbe;margin-left:10px}
.ghost:hover{background:#f0e9dc;color:#232025}
nav{background:#fff;border-bottom:1px solid #e0d9cc;padding:11px 0;
 margin:-56px -28px 34px;position:sticky;top:0;z-index:9}
nav .in{max-width:1080px;margin:0 auto;padding:0 28px;display:flex;
 align-items:center;gap:14px;font-size:13px}
nav a{color:#7d7364;text-decoration:none;border-bottom:1px solid #d8cfbe}
nav a:hover{color:#232025}
.err{background:#fdf1ee;border-left:2px solid #c0705e;padding:15px 19px;
 border-radius:0 3px 3px 0;margin:20px 0}
.err b{display:block;margin-bottom:6px;color:#8c4436}
.hidden{display:none}
.rank{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:14px}
.rank td,.rank th{padding:8px 10px;border-bottom:1px solid #eae3d7}
.rank tr:first-child td{background:#fdf6ee;font-weight:600}
@media(prefers-color-scheme:dark){
 fieldset{border-color:#333039}
 input[type=text],input[type=date],input[type=time],select,textarea,
 .seg label{background:#1f1e23;border-color:#3d3a45;color:#e6e1d8}
 .seg label:has(input:checked){background:#2e2b35;border-color:#57525f}
 button{background:#e6e1d8;color:#17161a}button:hover{background:#fff}
 .ghost{background:transparent;color:#9b917f;border-color:#3d3a45}
 .ghost:hover{background:#2a2730;color:#e6e1d8}
 nav{background:#1f1e23;border-color:#333039}
 .err{background:#2b1f1c;border-left-color:#8c4436}
 .rank td,.rank th{border-color:#2b2930}.rank tr:first-child td{background:#241f1c}}
"""

NAV = ('<nav><div class="in"><b>命途</b>'
       '<a href="/">重新填写</a>'
       '<span style="margin-left:auto;color:#a1968a">'
       '数据只在本机计算，不出网</span></div></nav>')


def page(title, body, extra_css=""):
    return (f"<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(title)}</title>"
            f"<style>{FORM_CSS}{extra_css}</style></head><body>"
            f"<div class=\"wrap\">{body}</div></body></html>")


def form_page(prefill=None, error=None):
    p = prefill or {}
    cities = "".join(f'<option value="{c}">' for c in CITY_LON)
    err = ""
    if error:
        err = (f'<div class="err"><b>没能排出盘来</b>{html.escape(error)}</div>')

    def v(k, d=""):
        return html.escape(str(p.get(k, d)))

    return page("命途 — 排盘", f"""
<h1>命途</h1>
<div class="sub">八字与紫微斗数双轴推演，一辈子的曲线，不是一年的快照</div>
<div class="note" style="margin:0 0 26px">
 生辰只在这台机器上计算，<b>不出网</b>——没有上传、没有统计、没有任何对外请求。
 页面关掉就没了，除非你自己保存。</div>
{err}
<form method="post" action="/compute">
 <fieldset><legend>出生信息</legend>
  <div class="row">
   <div><label>姓名或称呼</label>
    <input type="text" name="name" value="{v('name','命主')}" placeholder="妈妈"></div>
   <div><label>性别　（决定大运顺逆，必填）</label>
    <div class="seg">
     <label><input type="radio" name="gender" value="男" {'checked' if p.get('gender')!='女' else ''}><span>男</span></label>
     <label><input type="radio" name="gender" value="女" {'checked' if p.get('gender')=='女' else ''}><span>女</span></label>
    </div></div>
  </div>
  <div class="row" style="margin-top:16px">
   <div><label>历法</label>
    <div class="seg">
     <label><input type="radio" name="cal" value="solar" {'checked' if p.get('cal')!='lunar' else ''}><span>公历</span></label>
     <label><input type="radio" name="cal" value="lunar" {'checked' if p.get('cal')=='lunar' else ''}><span>农历</span></label>
    </div>
    <p class="hint">五十岁以上的长辈报生日，默认往往是农历，问清楚再填。</p></div>
   <div><label>出生日期</label>
    <input type="text" name="ymd" value="{v('ymd')}" placeholder="1969-7-8" required></div>
   <div><label>出生时间　（钟表时间，不是时辰）</label>
    <input type="text" name="hm" value="{v('hm')}" placeholder="06:40"></div>
  </div>
  <div class="row" style="margin-top:16px">
   <div><label>出生城市　（做真太阳时校正，能填就填）</label>
    <input type="text" name="city" list="cities" value="{v('city')}" placeholder="丹东">
    <datalist id="cities">{cities}</datalist>
    <p class="hint">东西部差异可超过两个时辰。不在列表里就填经度。</p></div>
   <div><label>或直接填经度</label>
    <input type="text" name="lon" value="{v('lon')}" placeholder="124.38"></div>
  </div>
 </fieldset>

 <fieldset><legend>不知道几点</legend>
  <label style="display:flex;align-items:center;gap:9px;font-size:14px;color:inherit">
   <input type="checkbox" name="unknown_hour" value="1" style="width:auto"
          onchange="document.getElementById('ev').classList.toggle('hidden',!this.checked)">
   我不知道出生时辰，用已发生的事反推
  </label>
  <div id="ev" class="hidden" style="margin-top:14px">
   <label>一行一件事：年份　事情　好/坏</label>
   <textarea name="events" placeholder="1988 考上大学 好
1993 结婚 好
2001 下岗 坏
2009 手术住院 坏
2015 买房 好">{v('events')}</textarea>
   <p class="hint">至少三件，五件以上才有区分度。优先选被动发生的事（下岗、生病、家里变故），
   主动选择的事掺杂个人意志，区分度低。<br>
   如果十二个时辰分不开，它会直说"不可用"，不会挑一个假装知道。</p>
  </div>
 </fieldset>

 <fieldset><legend>口径</legend>
  <div class="row">
   <div><label>子时换日</label>
    <select name="sect">
     <option value="2" {'selected' if str(p.get('sect','2'))=='2' else ''}>晚子时法（默认，日柱仍属当日）</option>
     <option value="1" {'selected' if str(p.get('sect'))=='1' else ''}>早子时法（23 时后日柱算次日）</option>
    </select>
    <p class="hint">只影响 23:00–24:00 出生的人，但影响的是日主本身，全盘会换。</p></div>
   <div><label>真太阳时校正</label>
    <select name="tst">
     <option value="1" {'selected' if p.get('tst','1')=='1' else ''}>开启（推荐）</option>
     <option value="0" {'selected' if p.get('tst')=='0' else ''}>关闭，直接用钟表时间</option>
    </select></div>
   <div><label>推到多少岁</label>
    <input type="text" name="to_age" value="{v('to_age','90')}"></div>
  </div>
 </fieldset>

 <button type="submit">排盘</button>
 <button type="submit" name="mode" value="today" class="ghost">只看今日运势</button>
</form>

<footer>
仅供传统文化研究与自我参照，不构成医疗、投资、婚姻、法律等任何决策依据。<br>
不算生死，不推寿元。命盘描述的是结构性倾向，不是概率，更不是事实。
</footer>""")


def parse_events(raw):
    """One line per event: 年份 事情 好/坏"""
    events = []
    for line in (raw or "").splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].strip("年").isdigit():
            continue
        year = int(parts[0].strip("年"))
        tail = parts[1:]
        val = 0
        if tail and tail[-1] in ("好", "坏", "+", "-", "吉", "凶"):
            val = 1 if tail[-1] in ("好", "+", "吉") else -1
            tail = tail[:-1]
        desc = "".join(tail)
        if desc:
            events.append({"year": year, "desc": desc, "valence": val,
                           "dim": classify(desc)})
    return events


def chart_args(f):
    cal = f.get("cal", "solar")
    ymd = (f.get("ymd") or "").strip().replace("/", "-").replace(".", "-")
    hm = (f.get("hm") or "").strip() or "12:00"
    if len(hm.split(":")) == 1:
        hm = f"{int(hm):02d}:00"
    lon = f.get("lon", "").strip()
    return SimpleNamespace(
        solar=ymd if cal == "solar" else None,
        lunar=ymd if cal == "lunar" else None,
        time=hm, gender=f.get("gender", "男"),
        name=(f.get("name") or "命主").strip(),
        city=(f.get("city") or "").strip() or None,
        lon=float(lon) if lon else None,
        no_tst=f.get("tst", "1") != "1", no_eot=False,
        hour_unknown=bool(f.get("unknown_hour")),
        sect=int(f.get("sect", 2)))


def hour_page(f, events, results, verdict, note):
    rows = "".join(
        f"<tr><td>{i}</td><td><b>{r['zhi']}时</b></td><td>{r['time']}</td>"
        f"<td>{r['pillars']}</td><td>日主{r['day_master']}·{r['strength']}</td>"
        f"<td>{r['geju']}</td><td>{r['score']:+.2f}</td></tr>"
        for i, r in enumerate(results, 1))
    top = results[0]
    cont = ""
    if verdict != "不可用":
        cont = (f'<form method="post" action="/compute" style="margin-top:26px">'
                + "".join(f'<input type="hidden" name="{k}" value="{html.escape(str(v))}">'
                          for k, v in f.items() if k != "unknown_hour")
                + f'<input type="hidden" name="hm" value="{top["time"]}">'
                  f'<button type="submit">按 {top["zhi"]}时 继续排盘</button>'
                  f'<a href="/" class="ghost" style="display:inline-block;'
                  f'padding:13px 30px;text-decoration:none;border-radius:3px;'
                  f'margin-left:10px;font-size:15px;letter-spacing:.14em;'
                  f'border:1px solid #d8cfbe;color:#7d7364">重新填写</a></form>')
    else:
        cont = ('<div class="note" style="margin-top:24px">'
                '时辰没有被区分开，不要挑第一名硬上。'
                '补更多可确认、且分散在不同领域的事件再试一次，'
                '或者按时辰未知处理——那样只能看年月日三柱，'
                '子女、晚运、紫微十二宫都谈不了。</div>')
    return page("命途 — 时辰反推", NAV + f"""
<h1>时辰反推</h1>
<div class="sub">十二个时辰各排一套盘，拿你给的 {len(events)} 件事打分</div>
<div class="err" style="background:#fdf6ee;border-left-color:#c9bda8">
 <b style="color:#8a6a2f">判定：{html.escape(verdict)}</b>{html.escape(note)}</div>
<table class="rank"><tr><th></th><th>时辰</th><th>取时</th><th>四柱</th>
<th>日主</th><th>格局</th><th>得分</th></tr>{rows}</table>
{cont}""")


class Handler(BaseHTTPRequestHandler):
    server_version = "mingtu"

    def log_message(self, fmt, *a):        # keep the console readable
        pass

    def _send(self, body, code=200):
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(form_page())
        else:
            self._send(page("404", NAV + "<h1>没有这个页面</h1>"), 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        f = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        try:
            self._send(self.compute(f))
        except Exception as exc:
            self._send(form_page(f, f"{type(exc).__name__}: {exc}"), 400)

    def compute(self, f):
        if f.get("unknown_hour"):
            events = parse_events(f.get("events"))
            if len(events) < 3:
                return form_page(f, "反推时辰至少需要三件事，"
                                    "每行写成「年份 事情 好/坏」，比如「2001 下岗 坏」。")
            a = chart_args(f)
            a.to_age = 60
            a.solar = a.solar or a.lunar
            results, verdict, note, _m, _r = rank_hours(a, events)
            for r in results:
                r.pop("_chart", None)
                r.pop("_life", None)
            return hour_page(f, events, results, verdict, note)

        a = chart_args(f)
        chart = build_chart(a)

        if f.get("mode") == "today":
            return today_page(chart)

        try:
            to_age = max(20, min(120, int(f.get("to_age", 90))))
        except ValueError:
            to_age = 90
        life = build_lifeline(chart, to_age, chart["meta"]["gender"])
        birth = life["meta"]["birth_year"]
        this_year = date.today().year
        start = max(birth, this_year - 8)
        return NAV_INJECT(build_html(chart, life, start, start + 24))


def NAV_INJECT(doc):
    return doc.replace("<body>", "<body>" + NAV, 1).replace(
        "</style>", "</style>", 1).replace(
        "<style>", "<style>" + """
nav{background:#fff;border-bottom:1px solid #e0d9cc;padding:11px 0;
 position:sticky;top:0;z-index:9}
nav .in{max-width:1080px;margin:0 auto;padding:0 28px;display:flex;
 align-items:center;gap:14px;font-size:13px}
nav a{color:#7d7364;text-decoration:none;border-bottom:1px solid #d8cfbe}
@media(prefers-color-scheme:dark){nav{background:#1f1e23;border-color:#333039}}
.wrap{padding-top:26px}
""", 1)


def today_page(chart):
    res = build_yunshi(chart, date.today(), 7)
    rows = "".join(
        f"<tr><td><b>{u['date']}</b></td><td>{u['ganzhi']}</td>"
        f"<td>{u['shishen_gan']}</td><td>{u['score']:+.2f}</td>"
        f"<td>{u['best']}</td><td>{u['worst']}</td></tr>"
        for u in res.get("upcoming", []))
    s = res["stacked"]
    layers = "".join(
        f"<tr><td>{lab}</td><td><b>{r['ganzhi']}</b></td><td>{r['shishen_gan']}</td>"
        f"<td>{r['weight']}</td><td>{r['score']:+.2f}</td>"
        f"<td>{r['best']}</td><td>{r['worst']}</td>"
        f"<td class=\"conf-{r['confidence']}\">{r['confidence']}</td></tr>"
        for lab, r in (("流年", res["year"]), ("流月", res["month"]),
                       ("流日", res["day"])))
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in res["day"]["notes"])
    dims = "".join(f"<div><b>{d}</b>{v:+.2f}</div>"
                   for d, v in s["dims"].items())
    return page("命途 — 今日运势", NAV + f"""
<h1>{html.escape(chart['meta']['name'])}　今日</h1>
<div class="sub">{date.today().isoformat()}　·
四柱 {' '.join(p['ganzhi'] for p in chart['bazi']['pillars'])}　·
用神 {'、'.join(chart['bazi']['yongshen']['favor'])}</div>

<h2>三层叠加</h2>
<table><tr><th></th><th>干支</th><th>十神</th><th>权重</th><th>分</th>
<th>最强</th><th>最弱</th><th>双盘一致度</th></tr>{layers}</table>
<div class="note">权重是有意这样设的：年 1.0、月 0.55、日 0.3。一天不决定什么，
好流日落在坏流年里也读不成行动信号。这次主导的是<b>{s['dominated_by']}</b>那一层。</div>

<h2>叠加后的六维</h2>
<div class="kv">{dims}</div>

<h2>今日结构接触</h2>
<ul style="font-size:14px;color:#5e5548">{notes or '<li>今天与本命盘没有强结构接触</li>'}</ul>

<h2>未来六天</h2>
<table><tr><th>日期</th><th>干支</th><th>十神</th><th>分</th>
<th>最强</th><th>最弱</th></tr>{rows}</table>

<footer>仅供传统文化研究与自我参照，不构成任何决策依据。</footer>""")


def run(args):
    host, port = "127.0.0.1", args.port
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{httpd.server_address[1]}"
    print(f"命途已启动：{url}")
    print("数据只在本机计算，不出网。按 Ctrl+C 停止。")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        httpd.server_close()
