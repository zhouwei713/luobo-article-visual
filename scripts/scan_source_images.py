#!/usr/bin/env python3
"""List the images and media an article references and flag the ones that cannot be fetched.

  python scripts/scan_source_images.py article.md
  python scripts/scan_source_images.py article.md --manifest out/asset_manifest.json

Each reference is classified as
  local        a file path that exists next to the article
  missing      a local path that does not exist
  expiring     a signed or session link that will not open outside the author's account
               (Feishu/Lark drive authcode links, S3/OSS/COS signatures, Expires= or token= query strings)
  remote       an ordinary public URL; still verify before use
  media-ref    a bare placeholder such as [demo.mp4] with no file attached

Exit code is 0 always; read the summary. With --manifest an asset_manifest.json skeleton is written,
keeping document order and the paragraph next to each image as adjacent_explanation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXPIRING = [
    re.compile(r"feishu\.cn/space/api/box/stream/download"),
    re.compile(r"internal-api-drive-stream\.(feishu|larksuite)"),
    re.compile(r"larksuite\.com/space/api/box/stream/download"),
    re.compile(r"[?&](X-Amz-Signature|Signature|x-oss-signature|q-signature|Expires|expires|token|authcode|code)="),
]
IMG_MD = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMG_HTML = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
MEDIA_REF = re.compile(r"^\s*\\?\[([^\]]+\.(?:mp4|mov|webm|gif|mp3|wav))\\?\]\s*$", re.I)


def classify(ref: str, base: Path) -> str:
    if re.match(r"^https?://", ref):
        return "expiring" if any(p.search(ref) for p in EXPIRING) else "remote"
    if ref.startswith("data:"):
        return "local"
    return "local" if (base / ref).exists() else "missing"


def neighbour_text(lines: list[str], index: int) -> str:
    for step in (-1, 1, -2, 2, -3, 3):
        j = index + step
        if 0 <= j < len(lines):
            t = lines[j].strip()
            if t and not t.startswith("!") and not t.startswith("```") and not IMG_MD.search(t):
                return re.sub(r"\\(.)", r"\1", t.lstrip("#").strip())[:160]
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("article", type=Path)
    ap.add_argument("--manifest", type=Path)
    args = ap.parse_args()
    text = args.article.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    base = args.article.resolve().parent
    section = ""
    items = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            section = re.sub(r"\\(.)", r"\1", line.lstrip("#").strip())
        refs = [m.group(2) for m in IMG_MD.finditer(line)] + [m.group(1) for m in IMG_HTML.finditer(line)]
        for ref in refs:
            items.append({"kind": classify(ref, base), "ref": ref, "line": i + 1, "section": section,
                          "adjacent_explanation": neighbour_text(lines, i)})
        m = MEDIA_REF.match(line)
        if m:
            items.append({"kind": "media-ref", "ref": m.group(1).replace("\\", ""), "line": i + 1, "section": section,
                          "adjacent_explanation": neighbour_text(lines, i)})

    counts: dict[str, int] = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    print("SOURCE_SCAN " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())) if items else "SOURCE_SCAN none")
    for it in items:
        short = it["ref"] if len(it["ref"]) < 70 else it["ref"][:60] + "..."
        print(f"  L{it['line']:<4} {it['kind']:<9} {it['section'][:18]:<18} {short}")
    unusable = counts.get("expiring", 0) + counts.get("missing", 0) + counts.get("media-ref", 0)
    if unusable:
        print(f"ACTION {unusable} reference(s) cannot be used as evidence here. Ask the author once for the original "
              "files; if they are not supplied, build typographic cards instead and record the gap in asset_manifest.json, "
              "never on the public images.")

    if args.manifest:
        assets = []
        for n, it in enumerate(items, 1):
            assets.append({
                "asset_id": f"asset-{n:02d}",
                "source_order": n,
                "source_location": f"{it['section']} (line {it['line']})",
                "source_ref": it["ref"],
                "availability": it["kind"],
                "adjacent_explanation": it["adjacent_explanation"],
                "content_role": "",
                "target_page": "",
                "fit_policy": "contain",
                "used": False,
                "unused_reason": "" if it["kind"] in ("local", "remote") else "not retrievable in this environment",
            })
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps({"assets": assets}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"MANIFEST {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
