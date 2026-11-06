#!/usr/bin/env python3
"""Check publishable copy in a visual package.

Scans note.md and every html/*.html page (visible text only) for:
  1. detached narration when narrative_voice is author-first-person
  2. internal production notes that must never appear on public images
  3. platform lead-off terms (Xiaohongshu by default blocks off-site contact prompts)
  4. banned_patterns: regex rules from requirements.json and the shared config file

Works for Xiaohongshu packages and for WeChat or X illustration packages (no note.md needed).

banned_patterns entries are a regex string or {"pattern": "...", "label": "...", "level": "error|warn"}.
Shared rules live in ~/.config/article-visual-director/config.json (or ARTICLE_VISUAL_CONFIG) under
"banned_patterns", so personal writing rules apply to every package. Warnings print but do not fail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


DEFAULT_FORBIDDEN = [
    "文章里说到",
    "文章里提到",
    "文章中提到",
    "原文提到",
    "原文说到",
    "原文展示",
    "作者提到",
    "作者说到",
    "作者发现",
    "文中提到",
    "文中展示",
]


DEFAULT_PUBLIC_IMAGE_FORBIDDEN = [
    "截图来自附件",
    "图片来自附件",
    "来自附件真实案例",
    "附件没有提供",
    "附件未提供",
    "未提供独立文件",
    "原始视频未单独提供",
    "原始视频文件未单独提供",
    "真实界面证据",
    "真实节点关系",
    "本页保留作者",
    "轨迹只用于说明",
    "轨迹仅作示意",
    "轨迹示意不代表实际成片",
    "素材缺失说明",
    "来源审计",
    "制作过程说明",
]


PLATFORM_FORBIDDEN = {
    "xiaohongshu": [
        "后台回复", "公众号后台", "加V", "加v", "加微信", "加我微信", "微信号", "VX", "vx",
        "私信领取", "私信我领", "扫码", "二维码", "评论区扣1领", "链接在评论区",
    ],
}


def load_shared_config() -> dict:
    import os
    candidates = []
    if os.environ.get("ARTICLE_VISUAL_CONFIG"):
        candidates.append(Path(os.environ["ARTICLE_VISUAL_CONFIG"]))
    candidates.append(Path.home() / ".config" / "article-visual-director" / "config.json")
    for cand in candidates:
        if cand.is_file():
            try:
                return json.loads(cand.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                return {}
    return {}


def normalize_patterns(items) -> list[dict]:
    rules = []
    for item in items or []:
        if isinstance(item, str):
            rules.append({"pattern": item, "label": item, "level": "error"})
        elif isinstance(item, dict) and item.get("pattern"):
            rules.append({"pattern": item["pattern"], "label": item.get("label", item["pattern"]),
                          "level": item.get("level", "error")})
    return rules


def detect_platform(requirements: dict) -> str:
    platform = str(requirements.get("platform", "")).lower()
    mode = str(requirements.get("mode", "")).lower()
    if platform == "xiaohongshu" or mode.startswith("xiaohongshu"):
        return "xiaohongshu"
    return platform


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "div", "section", "li", "br", "h1", "h2", "h3"}:
            self.parts.append("\n")
        if tag in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "section", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def load_requirements(root: Path) -> dict:
    path = root / "requirements.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"COPY_VOICE_ERROR invalid requirements.json: {exc}") from exc


def visible_text(path: Path) -> str:
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() != ".html":
        return content
    parser = VisibleTextParser()
    parser.feed(content)
    return parser.text()


def line_for_phrase(text: str, phrase: str) -> int:
    return text[: text.index(phrase)].count("\n") + 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    root = args.output_dir.resolve()
    requirements = load_requirements(root)

    configured = requirements.get("forbidden_narration", [])
    forbidden = list(dict.fromkeys([*DEFAULT_FORBIDDEN, *configured]))
    if requirements.get("narrative_voice") != "author-first-person":
        forbidden = []
    configured_public = requirements.get("public_image_forbidden_copy", [])
    public_forbidden = list(dict.fromkeys([*DEFAULT_PUBLIC_IMAGE_FORBIDDEN, *configured_public]))

    platform = detect_platform(requirements)
    allowed_terms = set(requirements.get("platform_terms_allowed", []))
    platform_forbidden = [t for t in PLATFORM_FORBIDDEN.get(platform, []) if t not in allowed_terms]
    shared = load_shared_config()
    rules = normalize_patterns(shared.get("banned_patterns")) + normalize_patterns(requirements.get("banned_patterns"))
    compiled = []
    for rule in rules:
        try:
            compiled.append((re.compile(rule["pattern"]), rule))
        except re.error as exc:
            raise SystemExit(f"COPY_VOICE_ERROR bad banned_patterns regex {rule['pattern']!r}: {exc}")

    files: list[Path] = []
    note = root / "note.md"
    if note.exists():
        files.append(note)
    html_files: list[Path] = []
    html_dir = root / "html"
    if html_dir.exists():
        html_files = sorted(html_dir.rglob("*.html"))
        files.extend(html_files)

    if not files:
        print("COPY_VOICE_FAIL no note.md or HTML files to inspect")
        return 1
    failures: list[tuple[Path, int, str]] = []
    for path in files:
        text = visible_text(path)
        for phrase in forbidden:
            if phrase in text:
                failures.append((path, line_for_phrase(text, phrase), phrase))

    public_failures: list[tuple[Path, int, str]] = []
    for path in files:
        text = visible_text(path)
        for phrase in public_forbidden:
            if phrase in text:
                public_failures.append((path, line_for_phrase(text, phrase), phrase))

    platform_failures: list[tuple[Path, int, str]] = []
    pattern_failures: list[tuple[Path, int, str, str]] = []
    warnings: list[tuple[Path, int, str, str]] = []
    for path in files:
        text = visible_text(path)
        for phrase in platform_forbidden:
            if phrase in text:
                platform_failures.append((path, line_for_phrase(text, phrase), phrase))
        for regex, rule in compiled:
            for match in regex.finditer(text):
                line = text[: match.start()].count("\n") + 1
                entry = (path, line, rule["label"], match.group(0))
                (warnings if rule["level"] == "warn" else pattern_failures).append(entry)

    for path, line, label, found in warnings:
        print(f"WARN {path.relative_to(root)}:{line}: {label}: {found!r}")

    if failures or public_failures or platform_failures or pattern_failures:
        print("COPY_VOICE_FAIL")
        for path, line, phrase in failures:
            print(f"{path.relative_to(root)}:{line}: {phrase}")
        for path, line, phrase in public_failures:
            print(f"{path.relative_to(root)}:{line}: public-image-meta: {phrase}")
        for path, line, phrase in platform_failures:
            print(f"{path.relative_to(root)}:{line}: platform-{platform}: {phrase}")
        for path, line, label, found in pattern_failures:
            print(f"{path.relative_to(root)}:{line}: banned-pattern {label}: {found!r}")
        return 1

    print(f"COPY_VOICE_PASS files={len(files)} warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
