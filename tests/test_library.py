"""Regression coverage for excluded variants and upgrading existing images."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import app_paths
import assets
import engine


class LibraryTests(unittest.TestCase):
    def test_nude_variant_uses_same_character_and_skill_support(self):
        card = dict(Id='裸体 测试角色', 種別=0, 出现=1, 削除=0, 裸=1, 所属=1,
                    识别名='角色', **{'技能１': 5, '技能２': 0})
        self.assertTrue(engine.displayable(card))
        self.assertTrue(engine.eligible(card, {'角色': object()}, {5: object()}))
        self.assertTrue(engine.eligible(card, {}, {5: object()}))
        self.assertFalse(engine.eligible(card, {'角色': object()}, {}))

    def test_formal_item_generic_and_second_part_cards_are_included(self):
        for kind in (0, 5, 10):
            for appearance in (1, 2, 3):
                card = dict(Id='示例卡', 種別=kind, 出现=appearance, 削除=0, 所属=2,
                            识别名='角色', **{'技能１': 5, '技能２': 0})
                self.assertTrue(engine.eligible(card, {}, {5: object()}))
        for changes in [dict(種別=88), dict(削除=88), dict(Id='测试 人物')]:
            self.assertFalse(engine.displayable(dict(card, **changes)))

    def test_item_descriptions_include_quoted_card_names(self):
        source = 'tree 卡牌情报 = {\n\t"长剑 示例" = {\n\t\t说明１ = "古老的剑",\n\t\t说明２ = "第一行\\n第二行",\n\t},\n};'
        self.assertEqual(assets.parse_item_info(source), {'长剑 示例': ['古老的剑', '第一行', '第二行']})
        source = source.replace('"长剑 示例"', '赫卡忒\u3000')
        self.assertIn('赫卡忒\u3000', assets.parse_item_info(source))

    def test_old_library_reports_missing_variants_and_keeps_existing_png(self):
        with tempfile.TemporaryDirectory(prefix='rance-library-') as folder:
            folder = Path(folder)
            ident = 'Lv1 示例'
            filename = hashlib.sha256(ident.encode('utf-8')).hexdigest()[:24] + '.png'
            Image.new('RGBA', (208, 312), '#123456').save(folder / filename)
            before = (folder / filename).read_bytes()
            (folder / 'manifest.json').write_text(json.dumps({ident: dict(file=filename)}))
            cards = {key: dict(Id=key, 種別=0, 出现=1, 削除=0, 裸=nude, 所属=1)
                     for key, nude in [(ident, 0), ('裸体 示例', 1)]}
            with patch.object(app_paths, 'IMAGE_DIR', folder), patch.object(engine, 'catalog', return_value=(cards, {})):
                self.assertEqual(assets.library_status(), dict(expected=2, ready=1, missing=1))
                self.assertEqual((folder / filename).read_bytes(), before)

    def test_broken_image_is_missing_even_when_manifest_entry_exists(self):
        with tempfile.TemporaryDirectory(prefix='rance-library-') as folder:
            folder = Path(folder)
            ident = '裸体 示例'
            filename = hashlib.sha256(ident.encode('utf-8')).hexdigest()[:24] + '.png'
            (folder / filename).write_bytes(b'broken PNG')
            (folder / 'manifest.json').write_text(json.dumps({ident: dict(file=filename)}))
            with patch.object(app_paths, 'IMAGE_DIR', folder):
                self.assertEqual(assets.cached_images(), {})


if __name__ == '__main__':
    unittest.main()
