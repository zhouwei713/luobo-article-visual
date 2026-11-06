"""Run with python -B -m unittest discover -s tests -v."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_prompt_contract as contract
import check_xiaohongshu_copy as copy
import build_xiaohongshu_preview as preview


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def prompt(self, body):
        return self.write("prompts/01.md", '---\nasset_id: 01\nmode: cover-only\nasset_type: cover\nplatform: wechat\nstyle: product-hero\naspect_ratio: 3:4\nvisible_text: true\ntext_policy: short-exact\nexact_text: 正确标题\noutput: images/01.png\n---\n' + body)

    def requirements(self):
        return dict(mode="cover-only", style="product-hero", aspect_ratio="3:4", visible_text=True, text_policy="short-exact", exact_text="正确标题")

    def test_metadata_does_not_satisfy_body_title(self):
        self.assertTrue(contract.validate_prompt(self.requirements(), self.prompt("错误标题")))

    def test_negated_fallback_is_allowed(self):
        self.assertEqual([], contract.validate_prompt(self.requirements(), self.prompt("正确标题。禁止使用 textless 策略。")))

    def test_positive_fallback_is_rejected(self):
        self.assertTrue(contract.validate_prompt(self.requirements(), self.prompt("正确标题。使用 textless 策略。")))

    def test_relative_prompt_match(self):
        data = {"assets": [{"prompt": "prompts/01.md", "style": "test"}]}
        self.assertEqual("test", contract.contract_for_prompt(data, self.root / "prompts/01.md", self.root)["style"])

    def test_duplicate_contract_rejected(self):
        with self.assertRaises(ValueError):
            contract.contract_for_prompt({"assets": [{"prompt": "01.md"}] * 2}, Path("01.md"))

    def test_string_boolean_rejected(self):
        data = self.requirements()
        data["visible_text"] = "false"
        self.assertTrue(contract.validate_prompt(data, self.prompt("正确标题")))

    def test_duplicate_frontmatter_rejected(self):
        path = self.prompt("正确标题")
        path.write_text(path.read_text().replace("style: product-hero", "style: product-hero\nstyle: product-hero"))
        self.assertTrue(any("duplicate frontmatter" in item for item in contract.validate_prompt(self.requirements(), path)))

    def test_unclosed_frontmatter_rejected(self):
        path = self.prompt("正确标题")
        text = path.read_text()
        path.write_text("\n".join(text.splitlines()[:-2]) + "\n正确标题")
        self.assertTrue(any("not closed" in item for item in contract.validate_prompt(self.requirements(), path)))

    def test_inline_html_phrase(self):
        parser = copy.VisibleTextParser()
        parser.feed("<p>截图来自<span>附件</span></p>")
        self.assertIn("截图来自附件", parser.text())

    def test_attributed_copy_still_checked(self):
        self.write("requirements.json", '{"narrative_voice":"attributed-source"}')
        self.write("html/01.html", "<p>截图来自附件</p>")
        with patch.object(sys, "argv", ["check", str(self.root)]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, copy.main())

    def test_empty_copy_fails(self):
        with patch.object(sys, "argv", ["check", str(self.root)]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, copy.main())

    def test_warm_workbench_is_light(self):
        with patch.object(preview, "sample_image_tone", return_value=(220, (220, 220, 220))):
            self.assertEqual("浅色编辑主题", preview.infer_theme({"style": "warm-workbench-map"}, {}, [], self.root)["label"])

    def test_selected_version_excludes_candidates(self):
        self.write("images/01-v1.png", "candidate")
        self.write("images/01-v2.png", "selected")
        self.write("delivery.json", json.dumps({"pages": [{"asset_id": "01", "image": "images/01-v2.png"}]}))
        pages = preview.find_pages(self.root)
        self.assertEqual(1, len(pages))
        self.assertEqual("01-v2.png", pages[0]["image"].name)

    def test_malformed_delivery_has_clear_error(self):
        self.write("delivery.json", "[]")
        with self.assertRaisesRegex(SystemExit, "pages array"):
            preview.find_pages(self.root)

    def test_incomplete_and_corrupt_package_fails_without_overwrite(self):
        self.write("note.md", "## 标题\n测试")
        self.write("images/01.png", "not a PNG")
        output = self.write("index.html", "previous good preview")
        with patch.object(sys, "argv", ["preview", str(self.root), "--require-images"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, preview.main())
        self.assertEqual("previous good preview", output.read_text())

    def test_nested_preview_paths(self):
        self.write("note.md", "## 标题\n测试")
        self.write("html/01.html", "<p>内容</p>")
        document, warnings = preview.build_html(self.root, self.root / "review/index.html", False)
        self.assertIn('src="../html/01.html"', document)
        self.assertTrue(warnings)

    def test_complete_package_passes_and_keeps_actual_ratio(self):
        from PIL import Image
        self.write("note.md", "## 标题\n测试\n## 正文\n正文内容\n## 标签\n#测试")
        self.write("requirements.json", '{"mode":"xiaohongshu-package"}')
        self.write("asset_manifest.json", "[]")
        self.write("brief.md", "## 一句话主张\n测试预览")
        self.write("plan.md", "| 页码 | 页面职责 |\n|---|---|\n| 01 | 封面 |")
        self.write("qa.md", "尺寸检查已完成，视觉检查待完成")
        self.write("prompts/01.md", "测试提示词")
        (self.root / "images").mkdir()
        Image.new("RGB", (160, 90), "white").save(self.root / "images/01.png")
        self.write("delivery.json", json.dumps({"pages": [{"asset_id": "01", "image": "images/01.png", "prompt": "prompts/01.md", "dimensions": [160, 90]}]}))
        document, warnings = preview.build_html(self.root, self.root / "index.html", True)
        self.assertEqual([], warnings)
        self.assertIn("aspect-ratio:160/90", document)
        self.assertIn("object-fit:contain", document)
        self.assertIn("视觉验收请查看质量记录", document)

    # ---- additions: copy rules, platform terms, validator alignment, imagegen helpers, source scan
    def test_banned_patterns_fail_and_warn(self):
        self.write("requirements.json", json.dumps({"banned_patterns": [
            {"pattern": "——|—", "label": "破折号"},
            {"pattern": "：", "label": "冒号", "level": "warn"}]}, ensure_ascii=False))
        self.write("html/02.html", "<p>要点：一句话——出整套</p>")
        out = io.StringIO()
        with patch.object(sys, "argv", ["check", str(self.root)]), contextlib.redirect_stdout(out), \
                patch.object(copy, "load_shared_config", return_value={}):
            code = copy.main()
        self.assertEqual(1, code)
        self.assertIn("banned-pattern 破折号", out.getvalue())
        self.assertIn("WARN", out.getvalue())

    def test_warn_only_pattern_passes(self):
        self.write("requirements.json", json.dumps({"banned_patterns": [{"pattern": "：", "label": "冒号", "level": "warn"}]}, ensure_ascii=False))
        self.write("html/02.html", "<p>要点：一句话</p>")
        out = io.StringIO()
        with patch.object(sys, "argv", ["check", str(self.root)]), contextlib.redirect_stdout(out), \
                patch.object(copy, "load_shared_config", return_value={}):
            self.assertEqual(0, copy.main())

    def test_xiaohongshu_platform_terms(self):
        self.write("requirements.json", '{"platform":"xiaohongshu"}')
        self.write("note.md", "## 标题\n测试\n## 正文\n后台回复设计获取\n## 标签\n#测试")
        out = io.StringIO()
        with patch.object(sys, "argv", ["check", str(self.root)]), contextlib.redirect_stdout(out), \
                patch.object(copy, "load_shared_config", return_value={}):
            self.assertEqual(1, copy.main())
        self.assertIn("platform-xiaohongshu", out.getvalue())

    def test_platform_terms_can_be_allowed(self):
        self.write("requirements.json", '{"platform":"xiaohongshu","platform_terms_allowed":["二维码"]}')
        self.write("html/02.html", "<p>二维码占位框</p>")
        with patch.object(sys, "argv", ["check", str(self.root)]), contextlib.redirect_stdout(io.StringIO()), \
                patch.object(copy, "load_shared_config", return_value={}):
            self.assertEqual(0, copy.main())

    def test_editorial_hierarchy_without_visual_mode_for_regular_style(self):
        path = self.write("prompts/01.md", "---\nasset_id: 01\nmode: cover-only\nasset_type: cover\nplatform: wechat\nstyle: product-hero\naspect_ratio: 3:4\nvisible_text: true\ntext_policy: editorial-hierarchy\nexact_text: 正确标题\noutput: images/01.png\n---\n一级主标题“正确标题”。二级文字“副标题”。")
        req = dict(self.requirements(), text_policy="editorial-hierarchy", allowed_text=["副标题"])
        self.assertEqual([], contract.validate_prompt(req, path))

    def test_tertiary_text_requires_guidance(self):
        path = self.write("prompts/01.md", "---\nasset_id: 01\nmode: cover-only\nasset_type: cover\nplatform: wechat\nstyle: product-hero\naspect_ratio: 3:4\nvisible_text: true\ntext_policy: editorial-hierarchy\nexact_text: 正确标题\noutput: images/01.png\n---\n一级主标题“正确标题”。二级文字“副标题”。")
        req = dict(self.requirements(), text_policy="editorial-hierarchy", tertiary_text=["关键词"])
        errors = contract.validate_prompt(req, path)
        self.assertTrue(any("三级" in e for e in errors))

    def test_short_exact_with_supporting_text(self):
        path = self.prompt("标题“正确标题”。小字“萝卜设计”。")
        req = dict(self.requirements(), allowed_text=["萝卜设计"])
        self.assertEqual([], contract.validate_prompt(req, path))

    def test_imagegen_front_matter_and_ratio(self):
        import imagegen
        meta, body = imagegen.split_front_matter("---\naspect_ratio: 3:4\noutput: images/01.png\n---\n正文提示词")
        self.assertEqual("3:4", meta["aspect_ratio"])
        self.assertEqual("正文提示词", body)
        self.assertAlmostEqual(0.75, imagegen.ratio_value("3:4"))
        with self.assertRaises(imagegen.GenError):
            imagegen.parse_target("1080*1440")

    def test_imagegen_rejects_inline_key(self):
        import imagegen
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(imagegen.GenError):
                imagegen.Generator({"provider": "hiapi", "api_key": "secret"}, allow_inline_key=False)

    def test_source_scan_flags_feishu(self):
        import scan_source_images as scan
        article = self.write("a.md", "# 标题\n说明文字\n![x](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=abc)\n\\[demo.mp4\\]\n")
        out = io.StringIO()
        with patch.object(sys, "argv", ["scan", str(article), "--manifest", str(self.root / "m.json")]), contextlib.redirect_stdout(out):
            scan.main()
        self.assertIn("expiring=1", out.getvalue())
        self.assertIn("media-ref=1", out.getvalue())
        data = json.loads((self.root / "m.json").read_text(encoding="utf-8"))
        self.assertEqual("expiring", data["assets"][0]["availability"])

    def test_preview_ignores_raw_candidates(self):
        from PIL import Image
        (self.root / "images").mkdir()
        Image.new("RGB", (30, 40)).save(self.root / "images/01-cover.png")
        Image.new("RGB", (30, 40)).save(self.root / "images/01-cover-raw.png")
        stems = [p["stem"] for p in preview.find_pages(self.root)]
        self.assertEqual(["01-cover"], stems)


if __name__ == "__main__":
    unittest.main()
