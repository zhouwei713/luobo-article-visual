# 更新记录

## 2026-11-06

- 新增 `scripts/imagegen.py`，独立调用 HiAPI、OpenAI、OpenAI 兼容接口、Gemini、即梦，可共用 luobo-design 和 luobo-ppt 的配置；密钥只从环境变量读取，记录原生尺寸和放大倍数，同一提示词不重复扣费
- 新增 `scripts/render_pages.py`，跨平台渲染 HTML 页面，检查溢出、安全边距、页脚碰撞、裁切文字和最小字号
- 新增 `scripts/scan_source_images.py`，识别飞书等拿不到的图片链接和视频占位，生成素材清单骨架
- `check_xiaohongshu_copy.py` 支持 `banned_patterns`（项目级和共享配置）、小红书导流词默认拦截，公众号和 X 配图包也能用
- `validate_prompt_contract.py` 与文档对齐，`editorial-hierarchy` 只在高概念海报时强制 `visual_mode`，三级文字改为按 `tertiary_text` 检查，`short-exact` 可带至多三条辅助文字
- 预览页忽略 `-raw` 候选图，并在页面卡片显示模型原生尺寸和放大倍数
- SKILL.md 增加快速路径、脚本一览、正文配图默认渲染路线、`candidates/` 目录约定、飞书素材处理、密钥处理规则
- 参考文档补充字号下限表、文字策略与校验脚本对应表、放大交付记录字段
- 新增配置模板 `templates/article-visual.config.example.json`，回归测试从 17 项增加到 28 项
