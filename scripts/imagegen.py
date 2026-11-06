#!/usr/bin/env python3
"""Generate one bitmap from a saved prompt file through a configured image API.

Usage
  python scripts/imagegen.py --prompt-file prompts/01-cover.md --root <package-dir>
  python scripts/imagegen.py --prompt "..." --ratio 3:4 --out images/01-cover.png --target 1080x1440

The prompt file's YAML front matter supplies aspect_ratio and output when the flags are absent.
Only the body below the front matter is sent to the model.

Config lookup (first found wins)
  1. --config PATH
  2. env ARTICLE_VISUAL_CONFIG
  3. <root>/article-visual.config.json, ./article-visual.config.json
  4. ~/.config/article-visual-director/config.json
  5. luobo-design and luobo-ppt configs, so one key serves all three skills
     (./luobo-design.config.json, ~/.config/luobo-design/config.json, ~/.config/luobo-ppt/config.json)

Config example
  {"provider": "hiapi", "model": "gpt-image-2.5-flare/text-to-image",
   "api_key_env": "HIAPI_API_KEY", "resolution": "2K", "timeout": 300}

Secrets
  The key is read from the environment variable named by api_key_env. A literal "api_key" in a
  config file is ignored unless --allow-inline-key is passed. The key is never written to any
  output, sidecar or log.

Outputs
  <out>                 final image (resized to --target when given)
  candidates/<stem>-raw.<ext>   native model output when a resize happened
  <out minus suffix>.gen.json   provider, model, task id, prompt hash, native and final size

Reuse
  If the sidecar shows the same prompt hash, model and target, the paid call is skipped.
  Pass --force to generate again.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

DEFAULTS = {
    "hiapi": {"base_url": "https://api.hiapi.ai", "model": "gpt-image-2.5-flare/text-to-image", "api_key_env": "HIAPI_API_KEY"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-image-2", "api_key_env": "OPENAI_API_KEY"},
    "openai_compatible": {"api_key_env": "IMAGE_API_KEY"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "model": "gemini-3.1-flash-image", "api_key_env": "GEMINI_API_KEY"},
    "ark": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "doubao-seedream-4-0-250828", "api_key_env": "ARK_API_KEY"},
}
HIAPI_RATIOS = {"1:1": 1, "3:2": 1.5, "2:3": 2 / 3, "4:3": 4 / 3, "3:4": 3 / 4, "16:9": 16 / 9, "9:16": 9 / 16,
                "21:9": 21 / 9, "27:16": 27 / 16, "16:27": 16 / 27, "9:8": 9 / 8, "8:9": 8 / 9}
GEMINI_RATIOS = {"1:1": 1, "4:3": 4 / 3, "3:4": 3 / 4, "16:9": 16 / 9, "9:16": 9 / 16, "3:2": 1.5, "2:3": 2 / 3}


class GenError(RuntimeError):
    pass


# ------------------------------------------------------------------ config

def config_candidates(explicit: str | None, root: Path | None) -> list[Path]:
    cands: list[Path] = []
    if explicit:
        cands.append(Path(explicit))
    if os.environ.get("ARTICLE_VISUAL_CONFIG"):
        cands.append(Path(os.environ["ARTICLE_VISUAL_CONFIG"]))
    if root:
        cands.append(root / "article-visual.config.json")
    cands.append(Path.cwd() / "article-visual.config.json")
    home = Path.home()
    cands.append(home / ".config" / "article-visual-director" / "config.json")
    cands.append(Path.cwd() / "luobo-design.config.json")
    cands.append(home / ".config" / "luobo-design" / "config.json")
    cands.append(home / ".config" / "luobo-ppt" / "config.json")
    return cands


def load_config(explicit: str | None, root: Path | None, provider: str | None) -> dict:
    for cand in config_candidates(explicit, root):
        if cand.is_file():
            cfg = json.loads(cand.read_text(encoding="utf-8-sig"))
            cfg["_path"] = str(cand)
            if provider:
                cfg["provider"] = provider
            return cfg
    if explicit:
        raise GenError(f"config not found: {explicit}")
    if provider:
        return {"provider": provider, "_path": None}
    raise GenError("no image config found; create article-visual.config.json or pass --provider")


# ------------------------------------------------------------------ prompt

def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta: dict[str, str] = {}
            for line in lines[1:i]:
                m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
                if m:
                    meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
            return meta, "\n".join(lines[i + 1:]).strip()
    raise GenError("unclosed front matter in prompt file")


def ratio_value(ratio: str) -> float:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", ratio)
    if not m:
        raise GenError(f"bad ratio: {ratio}")
    return float(m.group(1)) / float(m.group(2))


# ------------------------------------------------------------------ providers

class Generator:
    def __init__(self, cfg: dict, allow_inline_key: bool):
        self.cfg = cfg
        self.provider = (cfg.get("provider") or "").lower()
        if self.provider not in DEFAULTS:
            raise GenError(f"unsupported provider: {self.provider!r}; use one of {', '.join(DEFAULTS)}")
        d = DEFAULTS[self.provider]
        self.base_url = (cfg.get("base_url") or d.get("base_url") or "").rstrip("/")
        self.model = cfg.get("model") or d.get("model")
        self.key_env = cfg.get("api_key_env") or d.get("api_key_env")
        self.api_key = os.environ.get(self.key_env or "", "")
        if not self.api_key and cfg.get("api_key"):
            if not allow_inline_key:
                raise GenError("config holds a literal api_key; move it to an environment variable "
                               f"named by api_key_env ({self.key_env}) or pass --allow-inline-key")
            self.api_key = cfg["api_key"]
        if not self.api_key:
            raise GenError(f"api key missing: set the environment variable {self.key_env}")
        if not self.base_url:
            raise GenError("base_url missing in config")
        self.timeout = int(cfg.get("timeout", 300))
        self.record: dict = {}

    def _requests(self):
        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:
            raise GenError("python package 'requests' is required") from exc
        return requests

    def _post(self, url: str, body: dict, headers: dict) -> dict:
        r = self._requests().post(url, json=body, headers=headers, timeout=min(self.timeout, 300))
        if r.status_code >= 400:
            raise GenError(f"HTTP {r.status_code}: {r.text[:400]}")
        return r.json()

    def _download(self, url: str) -> bytes:
        last = None
        for i in range(3):
            try:
                r = self._requests().get(url, timeout=120)
                r.raise_for_status()
                return r.content
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(2 * (i + 1))
        host = url.split("/")[2] if "//" in url else url
        raise GenError(f"image is ready but download from {host} failed ({last}); the task was charged, "
                       f"open the URL in a browser before it expires or allow {host}: {url}")

    def generate(self, prompt: str, ratio: str) -> bytes:
        return getattr(self, "_gen_" + self.provider)(prompt, ratio)

    def _gen_hiapi(self, prompt: str, ratio: str) -> bytes:
        requests = self._requests()
        target = ratio_value(ratio)
        ar = min(HIAPI_RATIOS, key=lambda k: abs(HIAPI_RATIOS[k] - target))
        inp = {"prompt": prompt[:8000], "aspect_ratio": ar, "resolution": self.cfg.get("resolution", "2K"),
               "background": self.cfg.get("background", "opaque")}
        extra = self.cfg.get("extra_input")
        if isinstance(extra, dict):
            inp.update(extra)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        r = requests.post(f"{self.base_url}/v1/tasks", json={"model": self.model, "input": inp}, headers=headers, timeout=60)
        if r.status_code == 400:
            m = re.search(r"resolution: value must be '([^']+)'", r.text)
            if m and m.group(1) != inp["resolution"]:
                self.record["resolution_downgraded"] = {"requested": inp["resolution"], "used": m.group(1)}
                inp["resolution"] = m.group(1)
                r = requests.post(f"{self.base_url}/v1/tasks", json={"model": self.model, "input": inp}, headers=headers, timeout=60)
        if r.status_code >= 400:
            raise GenError(f"HTTP {r.status_code}: {r.text[:400]}")
        js = r.json()
        task = (js.get("data") or {}).get("taskId") or js.get("taskId")
        if not task:
            raise GenError("no taskId in response")
        self.record.update({"task_id": task, "api_aspect_ratio": ar, "resolution": inp["resolution"]})
        deadline = time.time() + self.timeout
        wait = float(self.cfg.get("poll_seconds", 3))
        while time.time() < deadline:
            time.sleep(wait)
            q = requests.get(f"{self.base_url}/v1/tasks/{task}", headers=headers, timeout=60)
            if q.status_code >= 400:
                raise GenError(f"poll HTTP {q.status_code}: {q.text[:300]}")
            d = q.json().get("data") or q.json()
            status = d.get("status")
            if status == "success":
                outs = d.get("output") or []
                url = outs[0].get("url") if outs and isinstance(outs[0], dict) else (outs[0] if outs else None)
                if not url:
                    raise GenError("task finished without an image url")
                return self._download(url)
            if status == "fail":
                raise GenError(f"task {task} failed: {json.dumps(d.get('error'), ensure_ascii=False)[:300]}")
            wait = min(wait * 1.3, 10)
        raise GenError(f"task {task} still not done after {self.timeout}s; check it in the HiAPI console")

    def _gen_openai(self, prompt: str, ratio: str) -> bytes:
        target = ratio_value(ratio)
        sizes = {"1024x1024": 1, "1536x1024": 1.5, "1024x1536": 2 / 3}
        size = self.cfg.get("size") or min(sizes, key=lambda k: abs(sizes[k] - target))
        body = {"model": self.model, "prompt": prompt, "size": size, "n": 1, "quality": self.cfg.get("quality", "high")}
        js = self._post(f"{self.base_url}/images/generations", body, {"Authorization": f"Bearer {self.api_key}"})
        return self._decode(js["data"][0])

    def _gen_openai_compatible(self, prompt: str, ratio: str) -> bytes:
        target = ratio_value(ratio)
        sizes = {"1024x1024": 1, "1536x1024": 1.5, "1024x1536": 2 / 3}
        size = self.cfg.get("size") or min(sizes, key=lambda k: abs(sizes[k] - target))
        body = {"model": self.model, "prompt": prompt, "size": size, "n": 1,
                "response_format": self.cfg.get("response_format", "b64_json")}
        js = self._post(f"{self.base_url}/images/generations", body, {"Authorization": f"Bearer {self.api_key}"})
        return self._decode(js["data"][0])

    def _gen_ark(self, prompt: str, ratio: str) -> bytes:
        ar = ratio_value(ratio)
        w, h = (2048, int(2048 / ar)) if ar >= 1 else (int(2048 * ar), 2048)
        w, h = max(1024, w - w % 8), max(1024, h - h % 8)
        body = {"model": self.model, "prompt": prompt, "size": self.cfg.get("size", f"{w}x{h}"),
                "response_format": "b64_json", "watermark": False}
        js = self._post(f"{self.base_url}/images/generations", body, {"Authorization": f"Bearer {self.api_key}"})
        return self._decode(js["data"][0])

    def _gen_gemini(self, prompt: str, ratio: str) -> bytes:
        target = ratio_value(ratio)
        ar = min(GEMINI_RATIOS, key=lambda k: abs(GEMINI_RATIOS[k] - target))
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ar}}}
        js = self._post(f"{self.base_url}/models/{self.model}:generateContent", body, {"x-goog-api-key": self.api_key})
        for cand in js.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                data = part.get("inlineData") or part.get("inline_data")
                if data and data.get("data"):
                    return base64.b64decode(data["data"])
        raise GenError("no image in Gemini response")

    def _decode(self, item: dict) -> bytes:
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            return self._download(item["url"])
        raise GenError("response has neither b64_json nor url")


# ------------------------------------------------------------------ main

def parse_target(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    m = re.fullmatch(r"(\d+)x(\d+)", value.strip())
    if not m:
        raise GenError(f"bad --target {value!r}, expected WIDTHxHEIGHT")
    return int(m.group(1)), int(m.group(2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt-file", type=Path)
    src.add_argument("--prompt")
    ap.add_argument("--root", type=Path, help="package root; output paths in front matter are relative to it")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--ratio")
    ap.add_argument("--target", help="final pixel size, e.g. 1080x1440; the native image is kept in candidates/")
    ap.add_argument("--config")
    ap.add_argument("--provider")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--allow-inline-key", action="store_true")
    args = ap.parse_args()

    try:
        meta: dict[str, str] = {}
        if args.prompt_file:
            meta, prompt = split_front_matter(args.prompt_file.read_text(encoding="utf-8-sig"))
            root = args.root or (args.prompt_file.resolve().parent.parent if args.prompt_file.resolve().parent.name == "prompts" else Path.cwd())
        else:
            prompt = args.prompt
            root = args.root or Path.cwd()
        if not prompt.strip():
            raise GenError("prompt is empty")
        ratio = args.ratio or meta.get("aspect_ratio") or "1:1"
        out = args.out or (Path(meta["output"]) if meta.get("output") else None)
        if out is None:
            raise GenError("no output path; pass --out or set output in front matter")
        if not out.is_absolute():
            out = (root / out).resolve()
        target = parse_target(args.target or meta.get("target_size"))
        if target and abs(target[0] / target[1] - ratio_value(ratio)) > 0.01:
            raise GenError(f"--target {target[0]}x{target[1]} does not match ratio {ratio}")

        cfg = load_config(args.config, root, args.provider)
        gen = Generator(cfg, args.allow_inline_key)
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        sidecar = out.with_suffix(".gen.json")
        if sidecar.is_file() and out.is_file() and not args.force:
            old = json.loads(sidecar.read_text(encoding="utf-8"))
            if old.get("prompt_sha256") == digest and old.get("model") == gen.model and old.get("target_size") == (list(target) if target else None):
                print(f"REUSED {out} (same prompt and model; pass --force to pay for a new one)")
                return 0

        print(f"generating with {gen.provider}:{gen.model} ratio {ratio} ...", flush=True)
        started = time.time()
        raw = gen.generate(prompt, ratio)

        from PIL import Image  # noqa: PLC0415
        image = Image.open(io.BytesIO(raw))
        image.load()
        native = list(image.size)
        out.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "provider": gen.provider,
            "model": gen.model,
            "config_path": cfg.get("_path"),
            "prompt_file": str(args.prompt_file) if args.prompt_file else None,
            "prompt_sha256": digest,
            "requested_ratio": ratio,
            "native_size": native,
            "target_size": list(target) if target else None,
            "seconds": round(time.time() - started, 1),
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **gen.record,
        }
        if target and tuple(native) != target:
            cand_dir = root / "candidates"
            cand_dir.mkdir(parents=True, exist_ok=True)
            raw_path = cand_dir / f"{out.stem}-raw{out.suffix or '.png'}"
            raw_path.write_bytes(raw)
            from PIL import ImageFilter  # noqa: PLC0415
            final = image.convert("RGB").resize(target, Image.LANCZOS)
            scale = target[0] / native[0]
            if scale > 1.05:
                final = final.filter(ImageFilter.UnsharpMask(radius=1.2, percent=40, threshold=2))
            final.save(out)
            record.update({"final_size": list(target), "upscale": round(scale, 3),
                           "raw_copy": str(raw_path.relative_to(root)) if raw_path.is_relative_to(root) else str(raw_path)})
        else:
            if out.suffix.lower() in {".png", ""}:
                image.save(out.with_suffix(".png") if not out.suffix else out)
            else:
                out.write_bytes(raw)
            record.update({"final_size": native, "upscale": 1.0})
        sidecar.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        note = f" upscaled x{record['upscale']}" if record["upscale"] != 1.0 else ""
        print(f"SAVED {out} native {native[0]}x{native[1]} final {record['final_size'][0]}x{record['final_size'][1]}{note} in {record['seconds']}s")
        if record.get("resolution_downgraded"):
            print(f"NOTE account only allows {record['resolution_downgraded']['used']}; record this in qa.md")
        return 0
    except GenError as exc:
        print(f"IMAGEGEN_FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
