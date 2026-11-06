# 萝卜文章视觉 luobo-article-visual

> 丢一篇文章进来，拿回一套能直接发的封面、配图和小红书图文。

这是萝卜哥自己每天在用的文章视觉 skill，Skill 名叫 `article-visual-director`。它会先读懂文章在讲什么，再决定哪些图交给 AI 画、哪些图用 HTML 精确排字，最后把每一张成图打开检查一遍才交付。

公众号封面、X Article 横幅、正文配图、概念海报、小红书封面和多页教程图文都能做。Claude Code、Codex 和 Claude 网页版都能装。

[![文章视觉导演：让内容长出画面](assets/examples/thumbs/covers/editorial-system-landscape.jpg)](#封面结构图谱)

[看 7 张封面案例](#封面结构图谱) · [看 7 种视觉风格](#视觉风格图谱) · [更新记录](CHANGELOG.md)

## 它和直接让 AI 画图有什么区别

直接让模型画，常见的毛病是封面只剩一句口号，配图跟文章对不上，数字和中文一多就出错字。这个 skill 主要在这几个地方下了功夫。

| 常见问题 | 这里的做法 |
| --- | --- |
| 封面只剩一句口号 | 先从文章里找出主张、冲突和视觉锚点，再组织画面和标题层级 |
| 配图和文章内容脱节 | 每张图对应文章里具体的输入、动作、输出和边界 |
| 数字、价格、步骤容易写错 | 这类图默认用 HTML 排字，每个数字和原文一字不差 |
| 小红书教程截图和说明分开 | 建素材清单，截图和对应解释放在同一页 |
| 自己的经历被写成旁观转述 | 作者经历默认第一人称，有脚本专门检查 |
| 飞书导出的图片拿不到 | 先扫描文章里的图片链接，拿不到的会提醒你补发，不会假装用上 |
| 图上冒出导流词或你不想要的句式 | 小红书默认拦截后台回复、加V 这类说法，你的写作禁忌也能配置成自动检查 |
| 做完没法复核 | 需求契约、提示词、页面源文件和检查记录全部留档 |

## 安装

先把仓库克隆下来。克隆时直接命名成 `article-visual-director`，后面放进 skills 目录就不用再改名。

```bash
git clone https://github.com/zhouwei713/luobo-article-visual.git article-visual-director
```

**Claude Code**

```bash
cp -r article-visual-director ~/.claude/skills/
```

装好后开一个新会话，输入 `/article-visual-director`，或者直接说“帮我给这篇文章配图”就会触发。

**Codex**

macOS 和 Linux

```bash
cp -r article-visual-director ~/.codex/skills/
```

Windows PowerShell

```powershell
Copy-Item -Recurse -LiteralPath ".\article-visual-director" -Destination "$env:USERPROFILE\.codex\skills\"
```

新开任务后用 `$article-visual-director` 调用。

**Claude 网页版和桌面版**

把 `article-visual-director` 文件夹打成 zip，在 Claude 的技能设置里上传即可。

**其他支持 skill 的 Agent**

把整个文件夹放进对应 Agent 的 skills 目录，入口文件是 `SKILL.md`。

### 依赖

脚本需要 Python 3.9 以上。渲染 HTML 页面要装 Playwright，生图要装 requests 和 Pillow。

```bash
pip install playwright requests pillow
playwright install chromium   # 电脑上已经有 Chrome 或 Edge 的话可以跳过
```

## 接上生图模型

封面和场景类配图要用 AI 生图。复制配置模板到用户目录，改成你自己的接口，再把密钥设成环境变量。

```bash
mkdir -p ~/.config/article-visual-director
cp templates/article-visual.config.example.json ~/.config/article-visual-director/config.json
export HIAPI_API_KEY=你的key
```

模板默认是我在用的 HiAPI，模型 `gpt-image-2.5-flare/text-to-image`。HiAPI、OpenAI、OpenAI 兼容接口、Gemini 和即梦都支持，改 `provider` 和 `model` 就行。之前给萝卜设计或萝卜PPT配过接口的话，这里不用再配，会自动读那份。

密钥只从环境变量读，配置文件里写死的 key 默认不认，生成记录里也不会出现。

如果你的账号只能出 1K 图，脚本会自动放大到要求的尺寸，原图留在 `candidates/`，放大倍数写进记录，交付时会说明。

## 把你的写作禁忌也配进去

同一个配置文件里的 `banned_patterns` 是长期写作规则，每次交付前都会自动扫一遍图上的字和发布文案。模板里预置了几条我自己的习惯，按需删改。

```json
"banned_patterns": [
  {"pattern": "——|—", "label": "破折号"},
  {"pattern": "不是[^。！？\\n]{0,20}而是", "label": "不是…而是句式"},
  {"pattern": "[「」]", "label": "角括号引号"},
  {"pattern": "：", "label": "冒号", "level": "warn"}
]
```

`level` 写成 `warn` 的只提醒不拦。单个项目还想加规则，写进该项目 `requirements.json` 的 `banned_patterns`，两边会合并检查。

## 怎么用

把文章丢给 Agent，说清楚发在哪、要什么就行。下面几句可以直接改了用。

```text
帮我给这篇文章配几张公众号正文图，数字多的地方用排版做，别让 AI 画。
```

```text
把这篇文章做成小红书图文，封面用 HiAPI 生成，要真实摄影感，内页用 HTML 排。
```

```text
给这篇文章做一张公众号 2.35:1 封面，提炼一个四到八个字的短标题。
```

```text
只要提示词，帮我写封面和三张配图的生图提示词，不用出图。
```

没指定风格时，它会先给三个封面方向让你挑，只问这一次。你说“直接出图”或“自动决定”，它就自己选了开干。

更多可复现的例子见 [案例配方](references/examples.md)。

### 交付的东西

一个小红书教程图文包大概长这样。公众号配图包会少一些文件，没有发布文案和预览页。

```text
article-visuals/你的主题/
  index.html          整体预览页，文案、全部页面和检查结果都在这里
  note.md             标题、正文、标签和互动问题
  plan.md             每页的职责和信息
  requirements.json   比例、文字、风格这些硬约束
  asset_manifest.json 原文素材清单，哪些拿到了哪些没有
  prompts/            AI 图的提示词
  html/               排版页面的源文件，改字后可以重新导出
  images/             最终图片
  candidates/         模型原图和落选候选
  qa.md               检查记录
```

## 哪些图用 AI 画，哪些用排版

封面没有特殊要求时优先用 AI 生图。人物动作、产品场景、概念隐喻、强透视、空间纵深、拼贴和摄影质感，这些交给 AI 效果最好。AI 封面上的中文尽量压到四到八个字，交付前逐字核对。

长标题必须逐字准确，或者图里主要是数字、表格、参数、流程、截图标注的时候，改用 HTML 排字再导出 PNG。公众号的数据卡、计分板、价格对比这类配图也默认走排版。

排版页面有字号下限，手机上缩小看也要读得清。3:4 小红书卡片正文 28 到 32px，1600 宽的公众号配图正文 40px 以上。渲染脚本会按画布宽度自动检查，字太小、溢出、压到页脚都会报出来。

## 案例图集

点击图片可以看高清版本。

### 文章封面

公众号封面，近景纸页和胶片转化，暖色放映光把标题、镜头序列和摄影轨道连在一起。

[![公众号封面：提示词变成拍摄方案](assets/examples/thumbs/article-cover-wechat-seedance.jpg)](assets/examples/article-cover-wechat-seedance.png)

X Article 横幅，在 5:2 画幅里重新安排胶片弧线和标题留白。

[![X Article 横幅：提示词变成拍摄方案](assets/examples/thumbs/article-cover-x-seedance.jpg)](assets/examples/article-cover-x-seedance.png)

### 正文配图和概念海报

正文配图把输入对象、三条工作路径和交付结果放在同一张图里。

[![正文配图：办公 Agent 的三条工作路径](assets/examples/thumbs/article-illustration-ai-office.jpg)](assets/examples/article-illustration-ai-office.png)

概念海报用可拆装的巨型环和连续光线，表达模块接上之后形成完整工作路径。

[![概念海报：把能力接起来](assets/examples/thumbs/concept-poster-deepseek.jpg)](assets/examples/concept-poster-deepseek.png)

### 小红书图文

AI 封面用巨字透视、人物和跨地域场景抓第一眼。

<p><a href="assets/examples/xiaohongshu-cover-seko.png"><img src="assets/examples/thumbs/xiaohongshu-cover-seko.jpg" alt="短剧出海 AI 封面" width="600"></a></p>

同一套图文的 HTML 教程内页，原始操作截图和说明放在一起，原图 1080×1440。

<p><a href="assets/examples/xiaohongshu-inner-seko.png"><img src="assets/examples/thumbs/xiaohongshu-inner-seko.jpg" alt="短剧出海教程内页与操作截图" width="720"></a></p>

封面负责让人认出主题，内页负责讲清操作，两边共用深色底、暖色强调和同一套标题层级。

## 视觉风格图谱

内置 7 种主风格，每种有自己的材质、光线和适合的文章类型。

<table>
<tr>
<td width="50%"><a href="assets/examples/styles/human-story-editorial.png"><img src="assets/examples/thumbs/styles/human-story-editorial.jpg" alt="human-story-editorial 风格示例" width="380"></a><br><code>human-story-editorial</code><br>人物经历、文化观察和情绪观点。雨夜列车、旧照片和人物视线留下叙事悬念。</td>
<td width="50%"><a href="assets/examples/styles/product-hero.png"><img src="assets/examples/thumbs/styles/product-hero.jpg" alt="product-hero 风格示例" width="380"></a><br><code>product-hero</code><br>产品介绍和功能发布。原创红色装置做主体，纸张输入和图像输出解释用途。</td>
</tr>
<tr>
<td width="50%"><a href="assets/examples/styles/concept-metaphor.png"><img src="assets/examples/thumbs/styles/concept-metaphor.jpg" alt="concept-metaphor 风格示例" width="380"></a><br><code>concept-metaphor</code><br>行业判断、抽象观点和趋势分析。平面红纸折成立体形状，让观点有了看得见的样子。</td>
<td width="50%"><a href="assets/examples/styles/warm-workbench-map.png"><img src="assets/examples/thumbs/styles/warm-workbench-map.jpg" alt="warm-workbench-map 风格示例" width="380"></a><br><code>warm-workbench-map</code><br>教程、Skill、方法论和工作流。暖木桌面、折页和连接纸带把草稿、样张和成品串起来。</td>
</tr>
<tr>
<td width="50%"><a href="assets/examples/styles/dark-system-pulse.png"><img src="assets/examples/thumbs/styles/dark-system-pulse.jpg" alt="dark-system-pulse 风格示例" width="380"></a><br><code>dark-system-pulse</code><br>自动化、基础设施和系统状态。接点闭合、铜线脉冲和指示灯表现工作开始的瞬间。</td>
<td width="50%"><a href="assets/examples/styles/tactile-interface-collage.png"><img src="assets/examples/thumbs/styles/tactile-interface-collage.jpg" alt="tactile-interface-collage 风格示例" width="380"></a><br><code>tactile-interface-collage</code><br>内容生产、创意工具和社交传播。撕纸、照片、样张和夹子叠出蓝红交错的手感。</td>
</tr>
<tr>
<td width="50%"><a href="assets/examples/styles/high-concept-poster.png"><img src="assets/examples/thumbs/styles/high-concept-poster.jpg" alt="high-concept-poster 风格示例" width="380"></a><br><code>high-concept-poster</code><br>强观点、发布宣言和文字主导的海报。荧光黄、黑色巨字和折起的边框一起表达突破限制。</td>
<td width="50%"></td>
</tr>
</table>

做多平台或多页图文时，封面先定主风格，内页沿用颜色、字体气质和材质，再按每页要讲的信息换构图。

## 封面结构图谱

下面 7 张都是专门为这个 skill 生成的 AI 封面，主题都是“文章怎么变成视觉”。风格管颜色、材质和光线，结构管读者第一眼从哪里看进来，两者可以自由搭配。

### 单一主体 · 一篇文章，多种视觉

[![单一主体封面：一篇文章，多种视觉](assets/examples/thumbs/covers/single-hero.jpg)](assets/examples/covers/single-hero.jpg)

`single-hero` 让近景展开的纸页占满画面中心，适合产品、作品和工具介绍。

### 动作瞬间 · 封面，差这一眼

[![动作瞬间封面：封面，差这一眼](assets/examples/thumbs/covers/unfinished-moment.jpg)](assets/examples/covers/unfinished-moment.jpg)

`unfinished-moment` 抓住人物抬起红色样张的那一下，适合创作经历、人物故事和经验复盘。

### 概念冲突 · 好内容，别埋没

[![概念冲突封面：好内容，别埋没](assets/examples/thumbs/covers/conceptual-tension.jpg)](assets/examples/covers/conceptual-tension.jpg)

`conceptual-tension` 让一张红色封面从灰色纸堆里抽出来，适合观点、行业判断和抽象命题。

### 系统场景 · 把文章，做成图文

[![系统场景封面：把文章，做成图文](assets/examples/thumbs/covers/system-landscape.jpg)](assets/examples/covers/system-landscape.jpg)

`system-landscape` 让文字纸带穿过一台微型纸艺印刷机变成图文页面，适合教程、方法和工作流。

### 编辑型系统场景 · 文章视觉导演

[![编辑型系统场景封面：文章视觉导演](assets/examples/thumbs/covers/editorial-system-landscape.jpg)](assets/examples/covers/editorial-system-landscape.jpg)

`editorial-system-landscape` 用大标题立住文章身份，长卷穿过巨型印框变成山水，适合复杂工具、项目介绍和系统拆解。

### 作品证据拼贴 · 封面，拿作品说话

[![作品证据拼贴封面：封面，拿作品说话](assets/examples/thumbs/covers/evidence-collage.jpg)](assets/examples/covers/evidence-collage.jpg)

`evidence-collage` 把已经做好的作品当样张拼成实物场景，适合展示成果。界面证据类封面要用原始截图。

### 标题与主体共享空间 · 让封面，抓住第一眼

[![标题与主体共享空间封面：让封面，抓住第一眼](assets/examples/thumbs/covers/title-space.jpg)](assets/examples/covers/title-space.jpg)

`title-space` 用荧光黄底和黑色巨字立住第一层，一条胶片从字的留白里穿过去，适合短标题和强观点。

## 工作模式

一般不用自己选，它会按你的需求自动判断。想指定的话，在请求里写模式名就行。

| 模式 | 交付 |
| --- | --- |
| `cover-only` | 一张封面和提示词 |
| `illustrations-only` | 正文配图，默认三到五张 |
| `full-package` | 封面、正文配图、平台变体和检查结果 |
| `xiaohongshu-cover` | 小红书 3:4 封面 |
| `xiaohongshu-carousel` | 小红书多页图文 |
| `xiaohongshu-tutorial` | AI 封面加 HTML 教程内页，统一导出 3:4 PNG |
| `xiaohongshu-package` | 封面、多页图文、发布文案、预览页和完整检查 |
| `prompt-led-cover` | 按你给的完整提示词出图，不改你的硬约束 |
| `reference-led-cover` | 参照你给的参考图做版式和光线 |
| `prompt-only` | 只给提示词，不出图 |
| `revision` | 保留已定方向，只改你点名的地方 |

## 脚本

这些脚本 Agent 会自己调用，你也可以单独跑。

```bash
# 扫描文章里的图片和视频，标出飞书这类拿不到的链接
python scripts/scan_source_images.py article.md --manifest out/asset_manifest.json

# 生图前检查提示词和需求契约
python scripts/validate_prompt_contract.py --contract out/requirements.json --prompt out/prompts/01-cover.md

# 按配置调用生图接口，固定输出尺寸
python scripts/imagegen.py --prompt-file out/prompts/01-cover.md --target 1080x1440

# 把 html 页面渲染成 PNG，检查溢出、页脚碰撞和最小字号
python scripts/render_pages.py out

# 检查图上的字和发布文案
python scripts/check_xiaohongshu_copy.py out

# 生成整体预览页，加 --require-images 做最终交付检查
python scripts/build_xiaohongshu_preview.py out --require-images
```

`render_html_pages.ps1` 是早期的 Windows 渲染脚本，保留给旧流程，新任务用 `render_pages.py`。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `SKILL.md` | 入口，路由和核心工作流 |
| `references/` | 平台策略、风格库、页面结构、提示词编译和质量规则 |
| `scripts/` | 上面那几个脚本 |
| `templates/` | 生图和写作禁忌的配置模板 |
| `tests/` | 回归测试，`python -m unittest discover -s tests` |
| `agents/openai.yaml` | Codex 界面名称和默认调用词 |
| `assets/examples/` | README 里的案例图，`thumbs/` 是缩略图 |

## 设计想法

封面负责让人第一眼看懂，正文图负责补上关系、证据和下一步。每一张图都要回答读者的一个问题，图上的术语和数字都能在原文里找到。

## 许可

[MIT License](./LICENSE)
