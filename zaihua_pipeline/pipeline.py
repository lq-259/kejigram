#!/usr/bin/env python3
"""
Stage 2: Execute LLM plan with PER-SEGMENT TTS for perfect sync.
Each paragraph gets its own TTS audio → measured → concatenated.
Result: exact timeline, no estimation drift.
"""
import os, sys, re, json, subprocess, time, requests, html, base64
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

# ─── Config ───
ROOT = Path.cwd() / "zaihua_pipeline"
BASE = ROOT
MIMO_BASE = "https://api.xiaomimimo.com/v1"
MIMO_KEY = os.environ.get("MIMO_KEY", "")
CLONE_REF = Path(os.environ.get("CLONE_REF", "/root/视频/科技简报/tts_assets/refs/vo_EQHDJ201_5_ganyu_15.wav"))
CLONE_STYLE = os.environ.get("CLONE_STYLE", "保持参考音频的音色和自然节奏，语速略微加快约 1%。")
TTS_BACKEND = os.environ.get("TTS_BACKEND", "mimo_clone").strip().lower()
MILORA_TTS_URL = os.environ.get("MILORA_TTS_URL", "https://api.milorapart.top/apis/mbAIsc")

BRAND_PATTERNS = [
    r"🌸\s*在花频道\s*[·・|｜-]?\s*备用频道\s*[·・|｜-]?\s*投稿通道",
    r"🌸\s*在花频道",
    r"🍀\s*在花频道",
    r"在花频道\s*[·・|｜-]?\s*备用频道\s*[·・|｜-]?\s*投稿通道",
    r"在花频道",
    r"备用频道",
    r"投稿通道",
    r"@?zaihuapd",
    r"@?zaihuatg",
    r"@?zaihuabot",
    r"@?zaihua",
    r"[·・|｜-]?\s*英文频道",
    r"[·・|｜-]?\s*茶馆讨论",
]


def clean_public_text(text):
    text = html.unescape(str(text or ""))
    for pattern in BRAND_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ·・|｜-/，,。")
    return text


def is_bad_title(text):
    text = clean_public_text(text)
    if not text or len(text) < 4:
        return True
    return not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", text)


def title_from_spoken(text):
    text = clean_public_text(text)
    if "，" in text:
        text = text.split("，", 1)[0]
    if len(text) > 34:
        text = text[:33] + "…"
    return text


def load_env_file(path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def is_internal_source_url(href):
    href = str(href or "").lower()
    return any(token in href for token in [
        "t.me/zaihua",
        "t.me/zaihuapd",
        "t.me/zaihuatg",
        "t.me/zaihuabot",
    ])

def mimo_tts(text, outpath, voice, style="标准播音腔，语速平稳，吐字清晰，专业播音员风格。", max_retry=3):
    url = f"{MIMO_BASE}/chat/completions"
    payload = {
        "model": "mimo-v2.5-tts",
        "messages": [
            {"role": "user", "content": style},
            {"role": "assistant", "content": text},
        ],
        "audio": {"format": "wav", "voice": voice},
    }
    for attempt in range(max_retry):
        try:
            r = requests.post(url, timeout=180, headers={
                "api-key": os.environ.get("MIMO_KEY", MIMO_KEY),
                "Content-Type": "application/json",
            }, json=payload)
            if r.status_code == 200:
                data = r.json()
                audio = data.get("choices", [{}])[0].get("message", {}).get("audio", {})
                b64 = audio.get("data")
                if b64:
                    outpath.write_bytes(base64.b64decode(b64))
                    return True
            print(f"    [mimo tts] {r.status_code} | {r.text[:120]}")
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 5 * (2 ** attempt)))
                continue
        except Exception as e:
            print(f"    [mimo tts] {e}")
            time.sleep(min(30, 5 * (2 ** attempt)))
    return False

def mimo_clone(text, outpath, ref_path, style="保持参考音频的音色、节奏和腔调。", max_retry=3):
    url = f"{MIMO_BASE}/chat/completions"
    with open(ref_path, "rb") as f:
        ref_b64 = base64.b64encode(f.read()).decode()
    payload = {
        "model": "mimo-v2.5-tts-voiceclone",
        "messages": [
            {"role": "user", "content": style},
            {"role": "assistant", "content": text},
        ],
        "audio": {
            "format": "wav",
            "voice": f"data:audio/wav;base64,{ref_b64}",
        },
    }
    for attempt in range(max_retry):
        try:
            r = requests.post(url, timeout=300, headers={
                "api-key": os.environ.get("MIMO_KEY", MIMO_KEY),
                "Content-Type": "application/json",
            }, json=payload)
            if r.status_code == 200:
                data = r.json()
                b64 = data.get("choices", [{}])[0].get("message", {}).get("audio", {}).get("data")
                if b64:
                    outpath.write_bytes(base64.b64decode(b64))
                    return True
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 5 * (2 ** attempt)))
                continue
        except Exception as e:
            print(f"    [mimo clone] {e}")
            time.sleep(min(30, 5 * (2 ** attempt)))
    return False

def milora_manbo_tts(text, outpath, max_retry=3):
    """Generate Manbo-style speech with Milora's public mbAIsc endpoint."""
    url = f"{MILORA_TTS_URL}?{urlencode({'text': text})}"
    for attempt in range(max_retry):
        try:
            r = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                audio_url = data.get("url")
                if data.get("code") == 200 and audio_url:
                    audio = requests.get(audio_url, timeout=180, headers={"User-Agent": "Mozilla/5.0"})
                    if audio.status_code == 200 and audio.content:
                        outpath.write_bytes(audio.content)
                        return True
                    print(f"    [milora audio] {audio.status_code} | {audio.text[:120]}")
                else:
                    print(f"    [milora tts] {data}")
            else:
                print(f"    [milora tts] {r.status_code} | {r.text[:120]}")
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 5 * (2 ** attempt)))
                continue
        except Exception as e:
            print(f"    [milora tts] {e}")
            time.sleep(min(30, 5 * (2 ** attempt)))
    return False

def generate_tts_segment(text, outpath):
    """Generate one TTS segment using selectable backends.

    TTS_BACKEND:
    - mimo_clone: use Mimo voice clone reference audio, fallback to neutral Mimo TTS.
    - milora: use Milora Manbo API, fallback to Mimo voice clone.
    - mimo_style: use normal Mimo voice with a neutral news style prompt.
    - mimo_clone: use Mimo voice clone reference audio, fallback to neutral Mimo TTS.
    """
    backend = TTS_BACKEND
    if backend == "mimo_clone":
        if CLONE_REF.exists() and mimo_clone(text, outpath, CLONE_REF, style=CLONE_STYLE):
            return True
        print("    [tts] Mimo clone failed; falling back to neutral Mimo TTS")
        return mimo_tts(text, outpath, "冰糖", style="标准新闻口播，语速平稳，吐字清晰。")

    if backend == "milora":
        if milora_manbo_tts(text, outpath):
            return True
        print("    [tts] Milora failed; falling back to Mimo voice clone")
        if CLONE_REF.exists() and mimo_clone(text, outpath, CLONE_REF, style=CLONE_STYLE):
            return True
        print("    [tts] Mimo clone fallback failed; falling back to neutral Mimo TTS")
        return mimo_tts(text, outpath, "冰糖", style="标准新闻口播，语速平稳，吐字清晰。")

    if backend == "mimo_style":
        return mimo_tts(text, outpath, "冰糖", style="标准新闻口播，语速平稳，吐字清晰。")

    print(f"    [tts] Unknown TTS_BACKEND={backend}; falling back to Milora")
    if milora_manbo_tts(text, outpath):
        return True
    if CLONE_REF.exists() and mimo_clone(text, outpath, CLONE_REF, style=CLONE_STYLE):
        return True
    return mimo_tts(text, outpath, "冰糖", style="标准新闻口播，语速平稳，吐字清晰。")

def get_audio_duration(path):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)]).strip())

_HTML_PPT_ROOT = "/root/.config/opencode/skills/html-ppt"
_HTML_PPT = f"{_HTML_PPT_ROOT}/assets"
_HTML_PPT_TEMPLATE12 = f"{_HTML_PPT_ROOT}/templates/full-decks/weekly-report/style.css"


def parse_date_arg():
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("Usage: pipeline.py [--run] [YYYY-MM-DD]\n\nGenerate TTS, HTML, SRT, MP4, source_links.md, and optional WebDAV upload.\nDefaults to yesterday when no date is provided.\nUse fetch_telegram.py --force YYYY-MM-DD to refresh summaries before running.")
        sys.exit(0)
    for arg in sys.argv[1:]:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", arg):
            return arg
    return (datetime.now() - timedelta(days=1)).date().strftime("%Y-%m-%d")


def opening_line(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"今天是{dt.year}年{dt.month}月{dt.day}日，欢迎观看科技新闻简报。"


def truncate_body(text, max_chars=360):
    if len(text) <= max_chars:
        return text
    for sep in ['。', '！', '？', '.', '!', '?']:
        idx = text.rfind(sep, max_chars - 100, max_chars)
        if idx > 0:
            return text[:idx + 1]
    return text[:max_chars - 1] + '…'


def brief_chunks(text, max_items=3, max_chars=72):
    chunks = [clean_public_text(s) for s in re.split(r'[。！？!?；;，,]', text or '')]
    chunks = [s for s in chunks if len(s) >= 6]
    if not chunks:
        chunks = [clean_public_text(text or '')]
    out = []
    for chunk in chunks:
        if len(chunk) > max_chars:
            chunk = chunk[:max_chars - 1] + '…'
        if chunk and chunk not in out:
            out.append(chunk)
        if len(out) >= max_items:
            break
    return out or ["暂无足够公开信息，按口播内容展示。"]


def infer_focus(text):
    text = text or ""
    if re.search(r"AI|模型|大模型|OpenAI|Claude|Gemini|机器人|智能", text, re.I):
        return "模型能力、产品落地、成本变化与竞争格局"
    if re.search(r"芯片|GPU|CPU|半导体|英伟达|AMD|Intel|台积电|内存|DDR", text, re.I):
        return "算力供给、硬件迭代、供应链与价格走势"
    if re.search(r"漏洞|安全|攻击|泄露|隐私|加密|黑客", text, re.I):
        return "安全风险、修复进展、数据与隐私保护"
    if re.search(r"政策|监管|法案|法院|禁令|欧盟|政府", text, re.I):
        return "监管边界、合规成本与行业执行节奏"
    if re.search(r"融资|上市|收购|营收|裁员|投资|估值", text, re.I):
        return "商业化能力、资本流向与公司经营变化"
    return "事件进展、后续落地节奏与行业连锁反应"


def infer_impact_groups(text):
    text = text or ""
    groups = []
    rules = [
        (r"开发|API|开源|GitHub|代码|程序", "开发者"),
        (r"企业|公司|客户|SaaS|云|办公", "企业用户"),
        (r"手机|App|应用|消费者|用户|订阅", "普通消费者"),
        (r"芯片|GPU|CPU|服务器|数据中心|云", "云厂商与硬件供应链"),
        (r"安全|漏洞|隐私|泄露", "安全团队与受影响用户"),
        (r"监管|政策|法案|政府|合规", "平台方与合规团队"),
        (r"投资|融资|上市|估值|营收", "投资者与创业公司"),
    ]
    for pattern, label in rules:
        if re.search(pattern, text, re.I) and label not in groups:
            groups.append(label)
    return "、".join(groups[:3] or ["科技从业者", "相关企业", "普通用户"])


def build_news_brief(title, body, spoken):
    source = clean_public_text(body or spoken or title)
    combined = f"{title} {source} {spoken}"
    return {
        "重点内容": brief_chunks(source, max_items=3),
        "关注点": [infer_focus(combined)],
        "影响群体": [infer_impact_groups(combined)],
    }


def render_brief_cards(brief):
    labels = ["重点内容", "关注点", "影响群体"]
    cards = []
    for label in labels:
        items = brief.get(label) or []
        lis = "".join(f"<li>{html.escape(str(item))}</li>" for item in items)
        cards.append(f'<div class="news-brief-card"><div class="brief-label">{label}</div><ul>{lis}</ul></div>')
    return "".join(cards)


def render_cover_news_list(slides):
    news = [s for s in slides if s.get("type") == "news"]
    cls = "cover-news-list two-col" if len(news) > 6 else "cover-news-list"
    items = []
    for idx, slide in enumerate(news, 1):
        title = clean_public_text(slide.get("title") or slide.get("label") or f"新闻 {idx}")
        items.append(f'<li><span>{idx:02d}</span><b>{html.escape(title)}</b></li>')
    return f'<ol class="{cls}">{"".join(items)}</ol>'


def generate_html(plan, outpath, date_str):
    slides = plan["slides"]
    news_indices = {s.get("index") for s in slides if s["type"] == "news" and s.get("index") is not None}
    n_news = len(news_indices)
    total_pages = len(slides)
    parts = [f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<title>科技新闻简报 · {date_str}</title>
<link rel="stylesheet" href="{_HTML_PPT}/fonts.css">
<link rel="stylesheet" href="{_HTML_PPT}/base.css">
<link rel="stylesheet" href="{_HTML_PPT_TEMPLATE12}">
<style>
/* Self-contained fallback when html-ppt assets are not installed. */
:root{{
  --bg:#f5f1e8;
  --surface:#fffaf2;
  --text-1:#201a16;
  --text-2:#4f443b;
  --text-3:#827469;
  --accent:#cc4b2f;
  --border:rgba(32,26,22,.14);
  --radius:18px;
  --radius-lg:26px;
  --shadow:0 18px 50px rgba(58,42,28,.11);
  --grad:linear-gradient(180deg,#e45735,#ffb84d);
}}
html,body{{width:1920px;height:1080px;margin:0;overflow:hidden;background:var(--bg)}}
body.tpl-weekly-report{{font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',Arial,sans-serif;color:var(--text-1)}}
.deck{{position:relative;width:1920px;height:1080px;overflow:hidden;background:var(--bg)}}
.slide{{position:absolute;inset:0;width:100%;height:100%;box-sizing:border-box;display:none;flex-direction:column;overflow:hidden;opacity:0;background:radial-gradient(circle at 12% 10%,rgba(255,184,77,.28),transparent 30%),radial-gradient(circle at 82% 18%,rgba(204,75,47,.16),transparent 28%),linear-gradient(135deg,#fffaf2 0%,#f3eadc 52%,#eadfcc 100%)}}
.slide.is-active{{display:flex;opacity:1;z-index:2}}
h1,p,ol,ul,li{{box-sizing:border-box}}
.kicker{{font-family:'JetBrains Mono','Noto Sans SC',monospace;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);font-weight:800;font-size:18px}}
/* ── align with render_video.mjs — disable transitions, script controls instant switching ── */
.slide.is-active{{z-index:2}}
.slide{{transition:none!important;transform:none!important}}

/* ── Template 12 adaptations for 16:9 news video ── */
.tpl-weekly-report .slide{{padding:56px 84px 56px!important;color:var(--text-1)}}
.topbar,.footer{{display:flex;align-items:center;justify-content:space-between;color:var(--text-3);font-family:'JetBrains Mono',monospace;font-size:18px}}
.topbar{{margin-bottom:28px}}
.footer{{position:absolute;left:84px;right:84px;bottom:26px}}

.cover,.end{{justify-content:center;align-items:center;text-align:center}}

.cover .h1,.end .h1{{font-size:136px;line-height:.92;margin:10px 0 28px;text-align:center}}
.cover .lede,.end .lede{{font-size:34px;max-width:1200px;margin:0 auto 32px;line-height:1.45}}
.cover .kpi{{max-width:900px;margin:0 auto;text-align:left}}
.cover .kpi .value{{font-size:58px}}
.cover-panel{{width:100%;max-width:1580px;margin:auto 0;text-align:left}}
.cover-title-row{{display:flex;align-items:end;justify-content:space-between;gap:28px;margin-bottom:26px}}
.cover-title-row .cover-title{{font-size:76px;line-height:.98;font-weight:850;letter-spacing:-.055em;margin:0}}
.cover-title-row .cover-count{{flex:none;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px 22px;box-shadow:var(--shadow);font-weight:800;color:var(--accent);font-size:28px}}
.cover-news-list{{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr;gap:13px}}
.cover-news-list.two-col{{grid-template-columns:1fr 1fr;column-gap:22px;row-gap:12px}}
.cover-news-list li{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 17px;display:grid;grid-template-columns:54px 1fr;gap:13px;align-items:center;box-shadow:var(--shadow);min-height:58px}}
.cover-news-list li span{{font-family:'JetBrains Mono',monospace;font-size:18px;color:var(--accent);font-weight:800}}
.cover-news-list li b{{font-size:25px;line-height:1.22;font-weight:750;color:var(--text-1)}}
.cover-news-list.two-col li b{{font-size:22px;line-height:1.2}}

.news-stage{{flex:1;min-height:0;display:grid;grid-template-rows:auto 1fr;gap:24px}}
.news-title{{font-size:66px;line-height:1.08;font-weight:800;letter-spacing:-.04em;max-width:1500px}}
.brief-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;align-items:stretch}}
.news-brief-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:28px 30px;box-shadow:var(--shadow);position:relative;overflow:hidden}}
.news-brief-card::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--grad)}}
.brief-label{{font-size:18px;color:var(--accent);font-weight:800;letter-spacing:.06em;margin-bottom:16px}}
.news-brief-card ul{{margin:0;padding-left:1.1em}}
.news-brief-card li{{font-size:30px;line-height:1.38;font-weight:650;margin:0 0 12px;color:var(--text-1)}}
.image-popover{{position:fixed;inset:0;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55);padding:0;z-index:99;opacity:0;transition:none;pointer-events:none;overflow:hidden}}
.image-popover.on{{opacity:1}}
.image-popover img{{width:auto;height:auto;max-width:66.666vw;max-height:100vh;object-fit:contain;object-position:center center;background:#000}}
.image-popover img.landscape{{width:66.666vw;height:auto;max-height:100vh}}
.image-popover img.portrait{{height:100vh;width:auto;max-width:66.666vw}}
.image-popover .caption{{display:none}}
</style>
</head><body class="tpl-weekly-report">
<div class="deck" id="deck">
"""]
    for page_no, slide in enumerate(slides, 1):
        cls = "cover" if slide["type"] == "cover" else "end" if slide["type"] == "end" else "slide news"
        did = "0" if slide["type"] == "cover" else ("end" if slide["type"] == "end" else str(slide.get("index", 0) + 1))
        extra = " is-active" if slide["type"] == "cover" else ""
        if slide["type"] == "cover":
            cover_news_html = render_cover_news_list(slides)
            parts.append(f'''<section class="slide cover{extra}" data-id="{did}" data-start="{slide['start']:.3f}" data-end="{slide['end']:.3f}">
<div class="topbar"><span class="kicker">tech news · daily brief</span><span>{page_no:02d} / {total_pages:02d}</span></div>
<div class="cover-panel">
  <div class="kicker">{date_str} · 本次新闻列表</div>
  <div class="cover-title-row"><h1 class="cover-title">本次新闻</h1><div class="cover-count">{n_news} 条</div></div>
  {cover_news_html}
</div>
<div class="footer"><span>TECH DAILY · {date_str}</span><span>{page_no:02d} / {total_pages:02d}</span></div>
</section>''')
        elif slide["type"] == "end":
            parts.append(f'''<section class="slide end{extra}" data-id="{did}" data-start="{slide['start']:.3f}" data-end="{slide['end']:.3f}">
<div class="topbar"><span class="kicker">end of brief</span><span>{page_no:02d} / {total_pages:02d}</span></div>
<div style="margin:auto 0;text-align:center">
  <div class="kicker">thanks for listening</div>
  <h1 class="h1">感谢<br>收听</h1>
  <p class="lede">以上是 {date_str} 的科技新闻简报，我们下期再见。</p>
</div>
<div class="footer"><span>数据来源 · 公开新闻频道</span><span>{page_no:02d} / {total_pages:02d}</span></div>
</section>''')
        else:
            title = clean_public_text(slide.get("title", slide.get("label", f"新闻 {slide.get('index', 0)+1}")))
            body = clean_public_text(slide.get("body", slide.get("lede", slide.get("text", ""))))
            body = truncate_body(body)
            imgs = slide.get("imgs", [])
            cur_page = page_no
            brief = slide.get("brief") or build_news_brief(title, body, slide.get("text", ""))
            cards_html = render_brief_cards(brief)
            popup = ""
            if imgs:
                pop_start = float(slide.get("image_popup_start", 0.8))
                pop_end = float(slide.get("image_popup_end", min(3.8, max(1.8, slide['end'] - slide['start']))))
                popup = f'''<div class="image-popover" data-pop-start="{pop_start:.3f}" data-pop-end="{pop_end:.3f}"><img src="{imgs[0]}" alt=""/><div class="caption">{html.escape(title)}</div></div>'''
            slide_body = f'''<section class="slide news{extra}" data-id="{did}" data-start="{slide['start']:.3f}" data-end="{slide['end']:.3f}" data-pop-start="{slide.get('image_popup_start', 0.8):.3f}" data-pop-end="{slide.get('image_popup_end', 3.0):.3f}">
<div class="topbar"><span class="kicker">news · {slide.get('index',0)+1:02d}</span><span>{cur_page:02d} / {total_pages:02d}</span></div>
<div class="news-stage">
  <h1 class="news-title">{html.escape(title)}</h1>
  <div class="brief-grid">{cards_html}</div>
</div>
{popup}
<div class="footer"><span>TECH NEWS · {html.escape(title[:34])}</span><span>{cur_page:02d} / {total_pages:02d}</span></div>
</section>'''
            parts.append(slide_body)
    parts.append('''</div><script>
document.querySelectorAll('.image-popover img').forEach((img) => {
  const classify = () => img.classList.add(img.naturalHeight > img.naturalWidth ? 'portrait' : 'landscape');
  if (img.complete) classify(); else img.addEventListener('load', classify, { once: true });
});
</script></body></html>''')
    outpath.write_text("".join(parts), encoding="utf-8")
    print(f"    HTML: {outpath}")

def split_sentences(text):
    """Split subtitles by comma, period, question mark, and exclamation mark.
    Avoid splitting on English '.' so model names like V2.5 and domains stay intact.
    Strips trailing punctuation from each subtitle."""
    parts = re.split(r'(?<=[，,。！？!?])', text)
    cleaned = []
    for s in parts:
        s = s.strip().rstrip('，,。！？!?')
        if s:
            cleaned.append(s)
    return cleaned

def fmt(t):
    ms = int(round((t - int(t)) * 1000))
    if ms >= 1000: ms -= 1000; t += 1
    s = int(t)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d},{ms:03d}"

def write_srt(entries, outpath):
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(f"{i}\n{fmt(e['start'])} --> {fmt(e['end'])}\n{e['text']}\n")
    outpath.write_text("\n".join(lines), encoding="utf-8")
    print(f"    SRT: {outpath} ({len(entries)} entries)")


def match_summary(text, summaries):
    """Match a broadcast paragraph to the best Telegram summary by keyword overlap."""
    if not summaries:
        return None

    def _extract_keywords(src):
        kw = set()
        for m in re.finditer(r'[\u4e00-\u9fff]+', src):
            w = m.group()
            for n in range(3, min(5, len(w) + 1)):
                for i in range(len(w) - n + 1):
                    kw.add(w[i:i+n])
        kw.update(re.findall(r'[A-Za-z]{4,}', src))
        return kw

    best, best_score = None, 0
    for s in summaries:
        src = s.get("title", "") + " " + s.get("body", "")
        kw = _extract_keywords(src)
        if not kw:
            continue
        score = sum(1 for w in kw if w in text)
        if score > best_score:
            best_score = score
            best = s
    return best if best_score >= 3 else None


def write_source_links(plan_slides, outpath, date_str):
    lines = [f"# 新闻来源链接", "", f"日期：{date_str}", ""]
    seen = set()
    news = []
    for s in plan_slides:
        if s.get("type") != "news":
            continue
        idx = s.get("index")
        if idx in seen:
            continue
        seen.add(idx)
        news.append(s)
    for idx, slide in enumerate(news, 1):
        title = clean_public_text(slide.get("title") or slide.get("label") or f"新闻 {idx}")
        lines.append(f"## 新闻 {idx}：{title}")
        srcs = [(href, label) for href, label in (slide.get("srcs") or []) if not is_internal_source_url(href)]
        if not srcs:
            lines.append("- 未抓取到外部来源链接")
        else:
            for href, label in srcs:
                label = clean_public_text(label) or href
                lines.append(f"- [{label}]({href})")
        lines.append("")
    outpath.write_text("\n".join(lines), encoding="utf-8")
    print(f"    Source links: {outpath}")


def main():
    load_env_file(ROOT / ".env")
    date_str = parse_date_arg()
    day_dir = ROOT / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    plan_path = day_dir / "zaihua-plan.json"
    
    # ── Stage 0: Fetch from Telegram ──
    summaries_path = day_dir / "summaries.json"
    fetch_script = ROOT / "fetch_telegram.py"
    if fetch_script.exists() and (not summaries_path.exists()):
        print("[0] Fetching Telegram channel data...")
        cmd = ["python3", str(fetch_script)]
        if date_str != (datetime.now() - timedelta(days=1)).date().strftime("%Y-%m-%d"):
            cmd.append(date_str)
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[WARN] fetch_telegram.py failed: {e}")
            print("       Continuing without fresh data...")
    
    script_path = day_dir / f"script_{date_str}.md"
    legacy_script_path = ROOT / f"script_{date_str}.md"
    if not script_path.exists() and legacy_script_path.exists():
        script_path = legacy_script_path
    if not script_path.exists():
        print(f"[ERR] Script not found: {day_dir / f'script_{date_str}.md'}")
        sys.exit(1)
    
    paras = [p.strip() for p in script_path.read_text(encoding="utf-8").split("\n\n") if p.strip()]
    paras = [re.sub(r"^(第[一二三四五六七八九十百千]+条|最后一条)\s*[,，:：]?\s*", "", p) for p in paras]
    if paras:
        paras[0] = opening_line(date_str)
    print(f"Target date: {date_str}")
    print(f"Script: {len(paras)} paragraphs")
    
    # ── Stage A: Per-paragraph TTS ──
    seg_dir = day_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    
    segments = []
    for i, para in enumerate(paras):
        seg_wav = seg_dir / f"seg_{i:02d}.wav"
        seg_mp3 = seg_dir / f"seg_{i:02d}.mp3"
        
        print(f"\n  [{i+1}/{len(paras)}] TTS: {para[:30]}...")
        
        ok = False
        if not seg_wav.exists():
            ok = generate_tts_segment(para, seg_wav)
        
        if not ok and seg_wav.exists():
            print(f"    Using cached: {seg_wav}")
            ok = True
        
        if not ok:
            print(f"    [ERR] TTS failed for para {i}")
            continue
        
        # Convert to MP3
        if not seg_mp3.exists():
            try:
                subprocess.run(["ffmpeg", "-y", "-i", str(seg_wav),
                               "-c:a", "libmp3lame", "-q:a", "4", str(seg_mp3)],
                              capture_output=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"    [WARN] MP3 conversion failed for segment {i}: {e}")
                continue
        
        dur = get_audio_duration(seg_mp3)
        print(f"    Duration: {dur:.3f}s")
        
        segments.append({
            "index": i,
            "text": para,
            "mp3": str(seg_mp3),
            "duration": dur,
        })
    
    if len(segments) != len(paras):
        print("[WARN] Some TTS segments failed, using fallback concatenation")
    
    # ── Stage B: Concatenate audio & build EXACT timeline ──
    print("\n[2] Building exact timeline from real audio durations...")
    
    # Build concat file list
    list_file = seg_dir / "concat_list.txt"
    with open(list_file, "w") as f:
        for seg in segments:
            # Escape single quotes in path
            p = seg["mp3"].replace("'", "'\\''")
            f.write(f"file '{p}'\n")
    
    manbo_path = day_dir / f"audio_manbo_{date_str}.mp3"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", str(manbo_path)
        ], capture_output=True, check=True)
        print(f"    Concatenated: {manbo_path}")
    except subprocess.CalledProcessError as e:
        print(f"[ERR] Audio concatenation failed: {e}")
        sys.exit(1)
    
    total_dur = get_audio_duration(manbo_path)
    print(f"    Total duration: {total_dur:.3f}s")
    
    # Load Telegram summaries for slide visuals (title/body/imgs)
    summaries = json.loads(summaries_path.read_text(encoding="utf-8")) if summaries_path.exists() else []


    # Build EXACT timeline
    cursor = 0.0
    plan_slides = []
    srt_entries = []
    news_counter = 0
    
    for i, seg in enumerate(segments):
        seg_start = cursor
        seg_end = cursor + seg["duration"]
        
        if i == 0:
            slide_type = "cover"
            idx = None
        elif i == len(segments) - 1:
            slide_type = "end"
            idx = None
        else:
            slide_type = "news"
            idx = news_counter
            news_counter += 1
        
        matched = match_summary(seg["text"], summaries)
        title = ""
        body = ""
        imgs = []
        srcs = []
        if matched:
            raw_title = matched.get("title") or matched.get("body", "")
            title = clean_public_text(raw_title.split("。", 1)[0].split("\n", 1)[0])
            if is_bad_title(title):
                title = title_from_spoken(seg["text"])
            body = clean_public_text(matched.get("body") or seg["text"])
            imgs = matched.get("_local_imgs", [])
            srcs = [
                [href, clean_public_text(label) or href]
                for href, label in matched.get("srcs", [])
                if not is_internal_source_url(href)
            ]
        if not title:
            title = title_from_spoken(seg["text"])
        
        if slide_type == "news":
            popup_duration = min(3.0, max(1.0, seg["duration"] * 0.28)) if imgs else 0.0
            popup_start = min(1.0, max(0.0, seg["duration"] - popup_duration)) if imgs else 0.0
            plan_slides.append({
                "type": "news",
                "layout": "structured",
                "index": idx,
                "label": seg["text"][:30],
                "text": seg["text"],
                "title": title,
                "body": body,
                "brief": build_news_brief(title, body, seg["text"]),
                "imgs": imgs,
                "srcs": srcs,
                "image_popup_start": popup_start,
                "image_popup_end": popup_start + popup_duration,
                "start": seg_start,
                "end": seg_end,
            })

            # SRT covers full segment
            sentences = split_sentences(seg["text"])
            if len(sentences) > 1:
                char_counts = [len(s) for s in sentences]
                total_chars = sum(char_counts)
                sent_cursor = seg_start
                for sent, cc in zip(sentences, char_counts):
                    sent_dur = seg["duration"] * cc / total_chars if total_chars > 0 else 0.5
                    srt_entries.append({
                        "start": sent_cursor,
                        "end": min(sent_cursor + sent_dur, seg_end),
                        "text": sent,
                    })
                    sent_cursor += sent_dur
            else:
                srt_entries.append({
                    "start": seg_start,
                    "end": seg_end,
                    "text": seg["text"],
                })
        else:
            # Cover/end: single slide covers full duration
            slide_data = {
                "type": slide_type,
                "layout": slide_type,
                "index": idx,
                "label": seg["text"][:30] if slide_type != "end" else "感谢收听",
                "text": seg["text"],
                "start": seg_start,
                "end": seg_end,
            }
            plan_slides.append(slide_data)
            
            # Captions span cover/end segments
            sentences = split_sentences(seg["text"])
            if len(sentences) > 1:
                char_counts = [len(s) for s in sentences]
                total_chars = sum(char_counts)
                sent_cursor = seg_start
                for sent, cc in zip(sentences, char_counts):
                    sent_dur = seg["duration"] * cc / total_chars if total_chars > 0 else 0.5
                    srt_entries.append({
                        "start": sent_cursor,
                        "end": min(sent_cursor + sent_dur, seg_end),
                        "text": sent,
                    })
                    sent_cursor += sent_dur
            else:
                srt_entries.append({
                    "start": seg_start,
                    "end": seg_end,
                    "text": seg["text"],
                })
        
        cursor = seg_end
    
    # Snap last end to total duration (fix tiny rounding errors)
    plan_slides[-1]["end"] = total_dur
    srt_entries[-1]["end"] = total_dur
    
    # Save plan
    plan = {
        "date_str": date_str,
        "total_duration": total_dur,
        "slides": plan_slides,
    }
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print("\n  Exact timeline:")
    for i, s in enumerate(plan_slides):
        print(f"    Slide {i}: {s['start']:.2f}s - {s['end']:.2f}s ({s['type']}: {s['label'][:30]})")

    # ── Stage C: Generate assets ──
    print("\n[3] Generating HTML...")
    html_path = day_dir / f"news_{date_str}.html"
    generate_html(plan, html_path, date_str)
    
    print("[4] Generating SRT...")
    srt_path = day_dir / f"subs_{date_str}.srt"
    write_srt(srt_entries, srt_path)
    
    # ── Stage D: Render video ──
    print("[5] Rendering video...")
    render_script = Path("/root/.config/opencode/skills/zaihua-video/scripts/render_video.mjs")
    if not render_script.exists():
        render_script = ROOT / "render_video.mjs"
    
    out_mp4 = day_dir / f"video_{date_str}.mp4"
    try:
        subprocess.run(["node", str(render_script),
                        "--html", str(html_path),
                        "--audio", str(manbo_path),
                        "--plan", str(plan_path),
                        "--srt", str(srt_path),
                        "--out", str(out_mp4)],
                       check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERR] Video rendering failed: {e}")
        sys.exit(1)
    
    print("[6] Generating source link file...")
    write_source_links(plan_slides, day_dir / "source_links.md", date_str)

    upload_webdav = os.environ.get("UPLOAD_WEBDAV", "1").strip().lower() not in ("0", "false", "no")
    if upload_webdav:
        print("[7] Uploading to WebDAV...")
        upload_script = Path("/root/.config/opencode/skills/zaihua-video/scripts/upload_webdav.py")
        if not upload_script.exists():
            upload_script = ROOT / "upload_webdav.py"
        try:
            subprocess.run([sys.executable, str(upload_script), date_str], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[WARN] WebDAV upload failed: {e}")
            print("       Continuing without upload...")
    else:
        print("[7] WebDAV upload skipped (UPLOAD_WEBDAV=0)")
     
    print(f"\n[done] {out_mp4}")
    sz = out_mp4.stat().st_size
    print(f"    Size: {sz//1024//1024}MB")

if __name__ == "__main__":
    main()
