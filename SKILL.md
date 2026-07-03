---
name: zaihua-video
description: 自动化新闻播报视频制作。从 Telegram 公开频道抓取昨日新闻，生成口播稿、逐段 TTS、同步字幕、html-ppt 风格幻灯片，并用 Puppeteer/ffmpeg 渲染视频。触发方式：/zaihua-video、/新闻视频、/做新闻播报视频、/新闻简报
---

# Zaihua Video Pipeline

用于制作每日“在花频道”科技新闻播报视频。当前稳定流程是：Telegram 公开页抓取新闻，人工/LLM 生成一段一条新闻的口播稿，脚本按段生成 cloned TTS，基于实测音频时长生成 slide timeline 和 SRT，最后逐帧截图合成 MP4。

## 当前架构

```
Telegram public preview
https://t.me/s/zaihuapd
        |
        v
fetch_telegram.py -> YYYY-MM-DD/summaries.json + YYYY-MM-DD/imgs/
        |
        v
YYYY-MM-DD/script_YYYY-MM-DD.md  # 开场 + 一条新闻一段 + 结束
        |
        v
pipeline.py           # per-paragraph TTS, measured timings, HTML, SRT
        |
        v
render_video.mjs      # Puppeteer screenshots + ffmpeg mux
        |
        v
YYYY-MM-DD/video_YYYY-MM-DD.mp4 + publishing assets
```

## 核心原则

1. 新闻抓取优先使用 Telegram 公开预览页 `https://t.me/s/zaihuapd`，不要默认回退到 RSSHub。
2. `summaries.json` 的顺序不等于口播顺序，不允许用数组下标硬匹配新闻。
3. 口播稿必须“一条新闻一段”，避免一段合并多个主题导致图片/标题匹配错误。
4. 默认不精选、不删减新闻；`summaries.json` 里抓到几条有效新闻，口播稿中间就写几条新闻。只有用户明确要求“精选/只做 N 条/忽略某类新闻”时才删减。
5. 标题不合理时必须由 agent 根据正文/回复/来源重新拟标题，不能直接使用 emoji、空标题、频道签名、投稿提示或明显不成标题的碎片。
6. 音频时长以每段 TTS 生成后的 `ffprobe` 实测为准，不能用字符数估算。
7. slide 切换按实测音频 paragraph boundary 执行，不能依赖浏览器 `timeupdate`。
8. HTML 显示内容可以来自 Telegram summary，字幕和音频始终来自 `script_YYYY-MM-DD.md`。
9. 如果 summary 匹配不够自信，HTML 回退显示口播文本，不能显示错题图文。
10. 字幕按逗号、句号、问号、感叹号分片，字幕文本末尾去掉 `，,。！？!?`。
11. 每天的素材必须放在对应日期目录下，例如 `/root/视频/科技简报/zaihua_pipeline/2026-06-06/`。
12. 抓取和生成阶段都要清洗 `在花频道`、`zaihua`、`zaihuapd`、投稿/备用频道等平台品牌词。
13. 当前视觉默认使用 html-ppt full-deck template 12：`weekly-report`。
14. 新闻页必须结构化呈现“重点内容 / 关注点 / 影响群体”，不要只铺原始正文。
15. 有图片的新闻不再拆单独图片页；图片必须在当前新闻页用弹窗/浮层方式显示 1 到 3 秒。
16. 每次视频生成完毕后，脚本只生成来源链接；短视频标题和封面必须由 agent 基于当天内容智能判断后写入。
17. `--help` / `-h` 必须无副作用，只打印帮助；不得抓取、覆盖、渲染或上传。
18. 用户说“重新抓取数据 / 重头生成 / 重头开始”默认只表示重新生成视频素材和 WebDAV 上传，不自动 B 站投稿；只有明确说“投稿 / 发布 / 继续投 / 完整发布流程”时才进入 B 站投稿技能。

## 文件结构

Skill 模板目录：

```
/root/.config/opencode/skills/zaihua-video/
├── SKILL.md
├── scripts/
│   ├── fetch_telegram.py
│   ├── pipeline.py
│   ├── upload_webdav.py
│   └── render_video.mjs
└── references/
    └── plan-schema.json
```

运行目录：

```
/root/视频/科技简报/zaihua_pipeline/
├── fetch_telegram.py
├── pipeline.py
├── render_video.mjs
├── upload_webdav.py
└── YYYY-MM-DD/
    ├── summaries.json
    ├── zaihua-plan.json
    ├── script_YYYY-MM-DD.md
    ├── subs_YYYY-MM-DD.srt
    ├── news_YYYY-MM-DD.html
    ├── audio_manbo_YYYY-MM-DD.mp3
    ├── video_YYYY-MM-DD.mp4
    ├── short_video_title.txt
    ├── source_links.md
    ├── cover_image.jpg
    ├── cover_selection.md
    ├── imgs/
    └── segments/
```

## 标准执行流程

### 1. 同步脚本到运行目录

```bash
mkdir -p /root/视频/科技简报/zaihua_pipeline
cp /root/.config/opencode/skills/zaihua-video/scripts/fetch_telegram.py /root/视频/科技简报/zaihua_pipeline/fetch_telegram.py
cp /root/.config/opencode/skills/zaihua-video/scripts/pipeline.py /root/视频/科技简报/zaihua_pipeline/pipeline.py
cp /root/.config/opencode/skills/zaihua-video/scripts/render_video.mjs /root/视频/科技简报/zaihua_pipeline/render_video.mjs
cp /root/.config/opencode/skills/zaihua-video/scripts/upload_webdav.py /root/视频/科技简报/zaihua_pipeline/upload_webdav.py
```

### 2. 抓取前一天 Telegram 新闻

```bash
python3 /root/视频/科技简报/zaihua_pipeline/fetch_telegram.py
```

默认不传日期参数，脚本自动抓取运行当天的前一天内容。只有补跑历史日期时才显式传入 `YYYY-MM-DD`：

```bash
python3 /root/视频/科技简报/zaihua_pipeline/fetch_telegram.py YYYY-MM-DD
```

如果当天 `summaries.json` 已存在，抓取脚本默认跳过，避免误覆盖。确认要重新抓取并覆盖时使用：

```bash
python3 /root/视频/科技简报/zaihua_pipeline/fetch_telegram.py --force YYYY-MM-DD
```

检查参数必须使用无副作用帮助：

```bash
python3 /root/视频/科技简报/zaihua_pipeline/fetch_telegram.py --help
python3 /root/视频/科技简报/zaihua_pipeline/pipeline.py --help
```

输出：

```bash
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/summaries.json
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/imgs/itemXX_imgY.jpg
```

抓取脚本会清洗正文中的平台品牌词，包括 `在花频道`、`zaihua`、`zaihuapd`、备用频道、投稿通道等。后续 `pipeline.py` 生成 HTML 时也会再清洗一次，兼容旧 `summaries.json`。

### 3. 生成口播稿

创建在对应日期目录：

```bash
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/script_YYYY-MM-DD.md
```

格式要求：

```markdown
今天是YYYY年M月D日，欢迎观看科技新闻简报。

第一条新闻……

第二条新闻……

第三条新闻……

以上就是今天的科技新闻简报，我们下期再见。
```

要求：

- 第一段是固定开场，格式必须为：`今天是YYYY年M月D日，欢迎观看科技新闻简报。`，日期以触发 pipeline 时确定的目标日期为准；`pipeline.py` 会在运行时自动覆盖第一段，避免口播稿手写不一致。
- 中间每段只讲一条新闻，默认覆盖 `summaries.json` 中全部有效新闻；不要默认只挑 5 条或做“精选”。
- 最后一段是结束。
- 口播稿默认使用短版写法：每条新闻只写 1 句，控制在约 45 到 70 个中文字符，结构为“发生了什么 + 最直接影响/看点”。
- 不要堆叠完整背景链、双方表态、历史沿革和过多数字；这些信息留给画面上的“重点内容 / 关注点 / 影响群体”。
- 只有用户明确要求深度版、长视频或详细解读时，才把单条新闻扩展到 2 到 3 句。
- 不要把两条新闻合进同一段。
- 不要在口播正文里保留“第一条/第二条/第三条”这类序号；需要排序时只体现在脚本段落顺序里，TTS 前必须去掉序号。
- 口播段落顺序可以是编辑顺序，不必等同 Telegram 顺序。
- 如果 Telegram title 是 emoji、空值、频道签名、投稿提示、链接说明或明显不合理标题，agent 必须读取 `body/reply_body/srcs` 后重新拟一个准确标题，并在口播稿和 HTML fallback 中使用合理标题。
- `pipeline.py` 也必须检测 emoji/空标题等无效标题，优先用口播段落生成标题 fallback，避免 `LM Studio 与苹果演示四台 Mac St` 这类硬截断标题。
- 只有在用户明确要求精选、控制时长、去掉非科技内容或跳过某类新闻时，才允许减少新闻条数。

### 4. 清理同日期旧 segment 音频

跨日期已经由日期目录隔离；如果同一天重写了口播稿，必须清理当天 `segments/`，避免复用同 index 的旧音频。

```bash
rm -f /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/segments/*.wav /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/segments/*.mp3
```

原因：同日期旧 `segments/seg_NN` 会导致新脚本复用过期音频，造成画面、字幕、声音错位。

### 5. 运行 pipeline 生成音频、SRT、HTML、plan

```bash
python3 /root/视频/科技简报/zaihua_pipeline/pipeline.py --run
```

默认不传日期参数，`pipeline.py` 自动使用运行当天的前一天日期；补跑历史日期时才显式传入 `YYYY-MM-DD`：

```bash
python3 /root/视频/科技简报/zaihua_pipeline/pipeline.py --run YYYY-MM-DD
```

如果脚本没有提供完整 CLI，可用 Python 直接调用内部函数，保留现有 `zaihua-plan.json` 时可只重建 HTML：

```bash
cd /root/视频/科技简报/zaihua_pipeline && python3 -c "
import json
from pathlib import Path
from pipeline import generate_html
root = Path('/root/视频/科技简报/zaihua_pipeline')
date_str = 'YYYY-MM-DD'
day = root / date_str
plan = json.loads((day / 'zaihua-plan.json').read_text())
generate_html(plan, day / f\"news_{date_str}.html\", date_str)
"
```

### 6. 渲染视频

```bash
node /root/视频/科技简报/zaihua_pipeline/render_video.mjs \
  --html /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/news_YYYY-MM-DD.html \
  --audio /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/audio_manbo_YYYY-MM-DD.mp3 \
  --plan /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/zaihua-plan.json \
  --srt /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/subs_YYYY-MM-DD.srt \
  --out /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/video_YYYY-MM-DD.mp4
```

### 7. 发布素材

`pipeline.py` 在视频渲染完毕后只自动生成来源链接：

```bash
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/source_links.md
```

规则：

- `source_links.md`：按“新闻 1、新闻 2、新闻 3……”列出对应外部来源链接。

视频生成完成后，agent 必须人工判断并写入：

```bash
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/short_video_title.txt
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/cover_image.*
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/cover_selection.md
```

agent 生成规则：

- `short_video_title.txt`：不要用脚本模板硬拼；阅读 `zaihua-plan.json`、`script_YYYY-MM-DD.md` 和关键新闻，写一个适合短视频平台的一行标题。
- `cover_image.*`：查看当天 `imgs/` 中的候选图片，结合新闻重要性、视觉冲击力、平台封面可读性选择一张复制出来。
- `cover_selection.md`：记录候选判断、最终选择的新闻序号、原图路径、封面路径和选择理由。

### 8. 上传到 WebDAV

`pipeline.py --run YYYY-MM-DD` 默认在生成 `source_links.md` 后自动上传当天目录到 WebDAV，远端保留 `zaihua_pipeline/YYYY-MM-DD/` 结构：

```bash
http://192.168.15.5:5244/dav/和彩云/视频/zaihua_pipeline/YYYY-MM-DD/
```

运行目录 `.env` 必须包含：

```bash
UPLOAD_WEBDAV=1
WEBDAV_BASE_URL=http://192.168.15.5:5244/dav
WEBDAV_REMOTE_ROOT=/和彩云/视频
WEBDAV_USERNAME=lqrobot
WEBDAV_PASSWORD=...
```

手动上传某一天：

```bash
python3 /root/视频/科技简报/zaihua_pipeline/upload_webdav.py YYYY-MM-DD
```

只预览待上传文件：

```bash
python3 /root/视频/科技简报/zaihua_pipeline/upload_webdav.py YYYY-MM-DD --dry-run
```

临时跳过上传：

```bash
UPLOAD_WEBDAV=0 python3 /root/视频/科技简报/zaihua_pipeline/pipeline.py --run YYYY-MM-DD
```

## Bilibili 投稿

视频生成并确认无误后，可执行 Bilibili 投稿流程。

### 1. 准备投稿素材

视频生成后，agent 必须人工判断并写入：

```bash
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/short_video_title.txt
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/cover_image.*
/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/cover_selection.md
```

生成规则：

- `short_video_title.txt`：阅读 `zaihua-plan.json`、`script_YYYY-MM-DD.md` 和关键新闻，写一个适合短视频平台的一行标题。
- `cover_image.*`：查看当天 `imgs/` 中的候选图片，结合新闻重要性、视觉冲击力、平台封面可读性选择一张复制出来。
- `cover_selection.md`：记录候选判断、最终选择的新闻序号、原图路径、封面路径和选择理由。

### 2. 执行投稿脚本

```bash
cd /root/视频/科技简报/zaihua_pipeline
node scripts/bilibili_upload_with_profile.js
```

脚本行为：

1. 启动 Chromium（加载已登录的 profile）
2. 打开 Bilibili 投稿页面
3. 自动上传视频文件
4. 自动填写标题、描述、标签
5. 自动选择"内容无需标注"
6. 自动点击"立即投稿"按钮
7. 等待投稿结果并关闭浏览器

### 3. 保存浏览器 profile

投稿完成后，保存 profile 以便下次使用：

```bash
tar -czf account-b-profile.tar.gz /tmp/bili_profile/account-b/
```

## HTML 视觉规范

当前默认风格：html-ppt full-deck template 12，`weekly-report`。

路径：

```bash
/root/.config/opencode/skills/html-ppt/templates/full-decks/weekly-report/style.css
```

关键要求：

- 页面使用 `--bg:#fafbfc` 近白背景、蓝→青渐变 accent、`.h1`/`.h2`/`.kicker`/`.lede`/`.card`/`.kpi` 等 class；字体为 `Inter` + `Noto Sans SC`。
- 封面页不再显示固定“科技简报”大标题，必须展示本次新闻标题列表；一列放不下时自动改为两列。
- 结束页内容水平、垂直居中。
- 新闻页标题正文要足够大，当前标题约 `64px`（`.h1`），正文约 `42px`（`.h2`）或通过 `.lede` 设置。
- 每条新闻页必须整理为结构化信息卡片，至少包含：`重点内容`、`关注点`、`影响群体`。
- `重点内容`、`关注点`、`影响群体` 三个信息卡片宽度必须一致，不允许重点内容列更宽。
- 必须禁用 `.slide` transition/transform，因为 renderer 逐帧强制切 slide。
- 不要依赖 CSS transition 或自动播放动画实现切页。
- 每条新闻默认只有一张 slide 覆盖该段完整时长。
- 一条新闻如果有图片，不允许新增图片 slide；必须在当前新闻页用 `.image-popover` 居中弹窗/浮层展示，图片必须完整显示不裁切；横图宽度约占屏幕三分之二，竖图高度对齐视频高度，显示时长 1 到 3 秒，并由 `render_video.mjs` 逐帧按 `data-pop-start/data-pop-end` 控制显隐。

## 匹配策略

`pipeline.py` 中 `match_summary(text, summaries)` 必须语义/关键词匹配，而不是 index 匹配。

推荐逻辑：

- 从口播段落和 summary 的 `title + body + reply_body` 提取关键词。
- 中文用 3 到 4 字滑窗短语，英文用 4 字符以上单词。
- 统计交集得分。
- 只有 `best_score >= 3` 才认为匹配成功。
- 匹配失败时，HTML title/body 使用口播文本 fallback。

这样可以处理 Telegram 页面新旧排序和编辑口播排序不一致的问题。

## 字幕策略

字幕来自口播稿，不来自 Telegram summary。

规则：

- 字幕必须“一句一句显示”：同一时间只显示当前一句/当前 clause，不能整段常驻，不能一次显示多句。
- 按 `，,。！？!?` 切句，逗号、句号、问号、感叹号都要切。
- 不要用英文句点 `.` 作为默认切分符，避免把 `V2.5`、域名、缩写拆坏；如果确认是普通英文句号，可由 agent 在口播稿中改写成中文句号。
- 每条字幕时间在对应新闻段的实测音频区间内按字符比例分配。
- 字幕末尾去除 `，,。！？!?`。
- 封面和结束页可显示对应开场/结束字幕。
- `render_video.mjs` 必须用 SRT/caption timeline 逐帧设置字幕，不要依赖浏览器 `timeupdate`；截图前直接写入当前字幕文本。

## 内容清洗

所有公开视频素材都要清洗频道品牌词，避免出现在画面标题、正文、来源标签和短视频标题里。

默认清洗：

- `在花频道`
- `zaihua`
- `zaihuapd`
- `zaihuatg`
- `zaihuabot`
- `备用频道`
- `投稿通道`
- 带 emoji 或分隔符的频道签名
- `英文频道`
- `茶馆讨论`

清洗位置：

- `fetch_telegram.py` 写入 `summaries.json` 前清洗。
- `pipeline.py` 生成 slide title/body/source label 前再次清洗。
- agent 写 `short_video_title.txt` 和 `cover_selection.md` 前必须再次清洗。

## TTS

当前支持三档 TTS 后端，通过环境变量 `TTS_BACKEND` 选择，默认是 `mimo_clone`。

```bash
TTS_BACKEND=mimo_clone  # 默认：小米 voice clone，参考音频见 CLONE_REF
TTS_BACKEND=milora      # 手动：Milora 曼波接口，失败后 fallback 到 Mimo voice clone
TTS_BACKEND=mimo_style  # 小米普通 TTS + 中性新闻口播 prompt，不传参考音频
```

Milora 曼波接口：

```bash
MILORA_TTS_URL=https://api.milorapart.top/apis/mbAIsc
GET https://api.milorapart.top/apis/mbAIsc?text=...
```

Mimo 配置：

```bash
MIMO_BASE=https://api.xiaomimimo.com/v1
model=mimo-v2.5-tts
voice=冰糖
voice clone reference=/root/视频/科技简报/tts_assets/refs/vo_EQHDJ201_5_ganyu_15.wav
CLONE_STYLE=保持参考音频的音色和自然节奏，语速略微加快约 1%。
```

注意：

- 生成时一段一个 TTS 文件，实测后 concat。
- TTS 成功后用 `ffprobe` 测量每段时长。
- 最终音频为 `audio_manbo_YYYY-MM-DD.mp3`。
- 默认链路是 Mimo voice clone，参考音频为 `/root/视频/科技简报/tts_assets/refs/vo_EQHDJ201_5_ganyu_15.wav`。
- 默认 clone style 是 `保持参考音频的音色和自然节奏，语速略微加快约 1%。`，可用 `CLONE_STYLE=...` 覆盖。
- `milora` 保留为手动后端：使用 Milora 曼波接口；如果 Milora 失败，再用 Mimo clone 参考音频兜底。
- `mimo_style` 只作为手动后备，不用于默认链路。
- `mimo_clone` 可用环境变量 `CLONE_REF=/path/to/ref.wav` 覆盖参考音频。每段都会上传参考音频，速度取决于 Mimo 接口。

## Puppeteer 依赖

`render_video.mjs` 当前固定加载：

```js
require('/tmp/puprec/node_modules/puppeteer')
```

如果报错 `MODULE_NOT_FOUND`，恢复依赖：

```bash
mkdir -p /tmp/puprec
cd /tmp/puprec
npm init -y
PUPPETEER_SKIP_DOWNLOAD=true npm install puppeteer@21.11.0 --omit=dev
```

不要安装 Puppeteer 25 到 Node 18 环境；它要求更高 Node 版本且 ESM 行为会导致 `ERR_REQUIRE_ESM`。

## 验证清单

生成后至少检查：

- `summaries.json` 昨日新闻条数合理。
- `script_YYYY-MM-DD.md` 中间段落是一条新闻一段。
- `zaihua-plan.json` slide 数量等于：封面 1 + 每条新闻 1 张结构化信息页 + 结束 1；有图新闻不能额外增加图片页。
- 每条 news slide 的 `data-start/data-end` 与音频段边界一致。
- 检查相邻 slide 的 `end/start` 没有大 gap。
- 新闻页包含“重点内容 / 关注点 / 影响群体”结构化卡片。
- “重点内容 / 关注点 / 影响群体”三列宽度一致。
- 有图新闻的图片以当前页居中弹窗/浮层出现，图片完整显示不裁切；横图宽度约占屏幕三分之二，竖图高度对齐视频高度，持续 1 到 3 秒，不单独切页。
- 封面页显示本次新闻列表，新闻多时两列排版，不显示固定“科技简报”作为主体内容。
- 新闻图文与口播主题一致，尤其注意 SpaceX/NASA、AMD/DDR5 这类相邻科技新闻不要错配。
- HTML、短视频标题里没有 `在花频道`、`zaihua`、`zaihuapd` 等品牌词。
- 字幕没有尾部句号/逗号。
- 字幕是一句一句显示，不是整段常驻。
- 封面页和结束页居中。
- `source_links.md` 按新闻 1、2、3 对应列出来源链接。
- `short_video_title.txt`、`cover_image.*` 和 `cover_selection.md` 已由 agent 判断后生成。
- 最终视频存在且音画同步：`/root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/video_YYYY-MM-DD.mp4`。
- 当 `UPLOAD_WEBDAV=1` 时，确认当天目录已上传到 `/和彩云/视频/zaihua_pipeline/YYYY-MM-DD/`。

## 常见问题

### 新闻顺序错乱

不要按 `summaries[index]` 取图文。用 `match_summary()`，失败就 fallback 到口播文本。

### 重新抓取数据但未投稿

“重新抓取数据 / 重头生成 / 重头开始”只跑新闻视频生成链路：抓取、口播稿、TTS、HTML、视频、WebDAV 上传。若用户还要 B 站发布，必须继续调用 Bilibili 投稿流程，例如“继续投”。

### 误运行帮助命令触发生成

这是脚本 bug。`fetch_telegram.py --help` 和 `pipeline.py --help` 必须只打印帮助，不允许产生任何文件或网络副作用。

### 音频还是旧内容

清空：

```bash
rm -f /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/segments/*.wav /root/视频/科技简报/zaihua_pipeline/YYYY-MM-DD/segments/*.mp3
```

日期目录已经解决跨日期复用；如果频繁重写同一天脚本，可进一步改为基于段落文本 hash 命名。

### HTML 切页有过渡残影

确保生成的 HTML 包含：

```css
.slide { transition: none !important; transform: none !important; }
```

### Puppeteer 找不到模块

按“Puppeteer 依赖”章节安装 `puppeteer@21.11.0` 到 `/tmp/puprec`。
