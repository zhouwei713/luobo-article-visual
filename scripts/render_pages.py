#!/usr/bin/env python3
"""Render every html/NN-*.html page in a package to images/NN-*.png and check it.

Works on Windows, macOS and Linux with Python Playwright.

  python scripts/render_pages.py <package-dir>
  python scripts/render_pages.py <package-dir> --include 03-step,05-result
  python scripts/render_pages.py <package-dir> --size 1600x900 --min-font 36

Canvas size comes from --size, then the page's <meta name="viewport" content="width=W,height=H">,
then requirements.json "canvas" (e.g. "1080x1440"), then 1080x1440.

Checks per page (any failure makes the exit code 1, the PNG is still written for review)
  - console errors and failed requests
  - horizontal or vertical document overflow beyond the canvas
  - visible elements crossing the canvas edge or the safe margin
  - content running into the footer (an element with data-footer or class "foot")
  - clipped text: elements whose content is taller or wider than their box while overflow is hidden
  - text smaller than the minimum font size; mark a deliberate small label with data-allow-small

Minimum font size defaults to round(canvas width x 0.022): 24px at 1080 wide, 35px at 1600 wide.
Override with --min-font or requirements.json "min_font_px".

Browser: env CHROME_PATH, then common Chrome/Edge/Chromium locations, then Playwright's bundled Chromium.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

CHECK_JS = r"""
({minFont, safe, width, height}) => {
  const issues = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > width + 1) issues.push(`document wider than canvas: ${doc.scrollWidth}px`);
  if (doc.scrollHeight > height + 1) issues.push(`document taller than canvas: ${doc.scrollHeight}px`);
  const footer = document.querySelector('[data-footer], .foot');
  const footerTop = footer ? footer.getBoundingClientRect().top : null;
  const label = el => {
    const t = (el.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 24);
    return `<${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''}> "${t}"`;
  };
  const seenSmall = new Set();
  let contentBottom = 0;
  for (const el of document.body.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    if (el.closest('[aria-hidden="true"], [data-decor]')) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const ownText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (ownText) {
      if (r.left < safe - 1 || r.top < safe - 1 || r.right > width - safe + 1 || r.bottom > height - safe + 1)
        issues.push(`text outside safe area (${safe}px): ${label(el)}`);
      const size = parseFloat(cs.fontSize);
      if (size + 0.01 < minFont && !el.closest('[data-allow-small], [data-footer], .foot')) {
        const key = `${Math.round(size)}|${label(el)}`;
        if (!seenSmall.has(key)) { seenSmall.add(key); issues.push(`font ${Math.round(size)}px < ${minFont}px: ${label(el)}`); }
      }
    }
    const clips = ['hidden', 'clip'].includes(cs.overflow) || ['hidden', 'clip'].includes(cs.overflowY) || ['hidden', 'clip'].includes(cs.overflowX);
    if (clips && ownText && (el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2))
      issues.push(`clipped text: ${label(el)}`);
    if (footer && !footer.contains(el) && !el.contains(footer) && ownText) contentBottom = Math.max(contentBottom, r.bottom);
  }
  if (footer && contentBottom > footerTop - 8) issues.push(`content runs into footer: bottom ${Math.round(contentBottom)} vs footer ${Math.round(footerTop)}`);
  return issues;
}
"""


def find_browser() -> str | None:
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    candidates = [
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def parse_size(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    m = re.search(r"(\d+)\s*[x×]\s*(\d+)", str(text))
    return (int(m.group(1)), int(m.group(2))) if m else None


def viewport_from_html(path: Path) -> tuple[int, int] | None:
    head = path.read_text(encoding="utf-8-sig")[:4000]
    m = re.search(r'name="viewport"\s+content="[^"]*width=(\d+)[^"]*height=(\d+)', head)
    return (int(m.group(1)), int(m.group(2))) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package", type=Path)
    ap.add_argument("--include", help="comma separated page stems or prefixes")
    ap.add_argument("--size", help="force canvas size, e.g. 1600x900")
    ap.add_argument("--min-font", type=float)
    ap.add_argument("--safe", type=float, default=0.03, help="safe margin as a fraction of the shorter side (default 0.03)")
    ap.add_argument("--report", type=Path, help="write a JSON report here (default <package>/render-report.json)")
    args = ap.parse_args()

    root = args.package.resolve()
    html_dir = root / "html"
    pages = sorted(p for p in html_dir.glob("*.html") if p.name.lower() != "index.html") if html_dir.is_dir() else []
    if args.include:
        wanted = [w.strip() for w in args.include.split(",") if w.strip()]
        pages = [p for p in pages if any(p.stem == w or p.stem.startswith(w) for w in wanted)]
    if not pages:
        print("RENDER_FAIL no html pages found")
        return 1

    req = {}
    if (root / "requirements.json").is_file():
        req = json.loads((root / "requirements.json").read_text(encoding="utf-8-sig"))

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("RENDER_FAIL python playwright is missing: pip install playwright")
        return 1

    (root / "images").mkdir(exist_ok=True)
    report = []
    failed = False
    browser_path = find_browser()
    with sync_playwright() as p:
        launch = {"executable_path": browser_path} if browser_path else {}
        browser = p.chromium.launch(**launch)
        for page_path in pages:
            size = parse_size(args.size) or viewport_from_html(page_path) or parse_size(req.get("canvas")) or (1080, 1440)
            w, h = size
            min_font = args.min_font or req.get("min_font_px") or round(w * 0.022)
            safe = round(min(w, h) * args.safe)
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            problems: list[str] = []
            page.on("console", lambda m, pr=problems: pr.append(f"console: {m.text}") if m.type == "error" else None)
            page.on("requestfailed", lambda r, pr=problems: pr.append(f"request failed: {r.url}"))
            page.goto(page_path.as_uri(), wait_until="networkidle")
            page.evaluate("async () => { if (document.fonts) await document.fonts.ready; }")
            if page.locator("[data-render-ready]").count():
                page.wait_for_selector('[data-render-ready="true"]', timeout=15000)
            problems += page.evaluate(CHECK_JS, {"minFont": min_font, "safe": safe, "width": w, "height": h})
            out = root / "images" / f"{page_path.stem}.png"
            page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
            page.close()
            status = "PASS" if not problems else "FAIL"
            failed |= bool(problems)
            print(f"{status} {page_path.stem} {w}x{h} min-font {min_font}px")
            for item in problems[:12]:
                print(f"   - {item}")
            if len(problems) > 12:
                print(f"   - ... {len(problems) - 12} more")
            report.append({"page": page_path.stem, "size": [w, h], "min_font_px": min_font,
                           "image": str(out.relative_to(root)), "status": status, "issues": problems})
        browser.close()
    report_path = args.report or (root / "render-report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(("RENDER_FAIL" if failed else "RENDER_PASS") + f" pages={len(report)} report={report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
