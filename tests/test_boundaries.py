import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import assets
import engine
import settings
import app_paths
from unittest.mock import patch


class BoundaryTests(unittest.TestCase):
    def test_table_parser_handles_quotes_and_newlines(self):
        text = 'table 例 = {\n { string Id, int 数值, string 说明 },\n { "a,b\\\"c", 7, "首行\\r次行" },\n};'
        self.assertEqual(assets.parse_table(text, '例'), [dict(Id='a,b"c', 数值=7, 说明='首行\r次行')])

    def test_parser_rejects_non_numeric_code(self):
        text = 'table 例 = {\n { int 数值 },\n { __import__("os") },\n};'
        with self.assertRaises(ValueError):
            assets.parse_table(text, '例')

    def test_game_fingerprint_rejects_other_version(self):
        with tempfile.TemporaryDirectory(prefix='rance-test-') as work:
            folder = Path(work)
            (folder / 'Rance10.exe').write_bytes(b'not-the-supported-game')
            with self.assertRaisesRegex(ValueError, '版本'):
                engine.validate_game(folder)

    def test_settings_keep_unicode_paths_without_rewriting_on_read(self):
        with tempfile.TemporaryDirectory(prefix='rance-test-') as work:
            target = Path(work) / '配置 空间'
            target.mkdir()
            with patch.object(app_paths, 'CONFIG_FILE', target / 'settings.json'), patch.object(settings, '_current', None):
                config = settings.save(target / '游戏', target / '存档', '')
                settings._current = None
                self.assertEqual(settings.load(), config)
                self.assertEqual(settings.save_dir(), target / '存档')
                before = hashlib.sha256(app_paths.CONFIG_FILE.read_bytes()).hexdigest()
                settings.load()
                self.assertEqual(hashlib.sha256(app_paths.CONFIG_FILE.read_bytes()).hexdigest(), before)

    def test_apply_rejects_stale_save_directory(self):
        with patch.object(engine, 'check_version'), patch.object(settings, 'save_dir', return_value=Path('expected-folder')):
            with self.assertRaisesRegex(ValueError, '目录'):
                engine.apply(Path('other-folder/LocalSave22.asd'), ['ignored'], 'ignored')


if __name__ == '__main__':
    unittest.main()
