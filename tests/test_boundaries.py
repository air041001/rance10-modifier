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
    def test_legacy_migration_keeps_new_cache_and_updates_cached_tool_path(self):
        import json
        with tempfile.TemporaryDirectory(prefix='rance-migrate-') as folder:
            old, new = Path(folder) / 'old', Path(folder) / 'new'
            (old / 'cache').mkdir(parents=True)
            (new / 'cache').mkdir(parents=True)
            (old / 'components').mkdir()
            (old / 'cache/catalog.json').write_text('old')
            (new / 'cache/catalog.json').write_text('new')
            (old / 'components/alice-0.13.0.exe').write_bytes(b'component')
            (old / 'settings.json').write_text(json.dumps(dict(alice_path=str(old / 'components/alice-0.13.0.exe'))))
            with patch.multiple(app_paths, LEGACY_DATA_DIR=old, DATA_DIR=new, CONFIG_FILE=new / 'settings.json',
                                COMPONENT_DIR=new / 'components', LOG_FILE=new / 'operations.jsonl'):
                app_paths.migrate_legacy()
                self.assertEqual((new / 'cache/catalog.json').read_text(), 'new')
                self.assertEqual(json.loads(app_paths.CONFIG_FILE.read_text(encoding='utf-8'))['alice_path'], str(new / 'components/alice-0.13.0.exe'))
                before = app_paths.CONFIG_FILE.read_bytes()
                app_paths.migrate_legacy()
                self.assertEqual(app_paths.CONFIG_FILE.read_bytes(), before)

    def test_missing_manual_component_uses_verified_cached_component(self):
        with tempfile.TemporaryDirectory(prefix='rance-test-') as folder:
            cached = Path(folder) / 'alice-0.13.0.exe'
            cached.write_bytes(b'fixture')
            with patch.object(app_paths, 'COMPONENT_DIR', Path(folder)), patch.object(assets, '_sha', return_value=assets.profile.ALICE_SHA256):
                self.assertEqual(assets.ensure_component(str(Path(folder) / 'no-longer-exists.exe')), cached)

    def test_table_parser_handles_quotes_and_newlines(self):
        text = 'table 例 = {\n { string Id, int 数值, string 说明 },\n { "a,b\\\"c", 7, "首行\\r次行" },\n};'
        self.assertEqual(assets.parse_table(text, '例'), [dict(Id='a,b"c', 数值=7, 说明='首行\r次行')])

    def test_parser_rejects_non_numeric_code(self):
        text = 'table 例 = {\n { int 数值 },\n { __import__("os") },\n};'
        with self.assertRaises(ValueError):
            assets.parse_table(text, '例')

    def test_game_directory_requires_inputs_without_a_version_whitelist(self):
        with tempfile.TemporaryDirectory(prefix='rance-test-') as work:
            folder = Path(work)
            for name in ['Rance10.exe', 'Rance10.ain', 'Rance10EX.ex']:
                (folder / name).write_bytes(b'non-baseline installation')
            self.assertEqual(engine.validate_game_directory(folder), Path(folder))
            (Path(folder) / 'Rance10.ain').unlink()
            with self.assertRaisesRegex(ValueError, 'Rance10.ain'):
                engine.validate_game_directory(folder)

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
        with patch.object(settings, 'save_dir', return_value=Path('expected-folder')):
            with self.assertRaisesRegex(ValueError, '目录'):
                engine.apply(Path('other-folder/LocalSave22.asd'), ['ignored'], 'ignored')


if __name__ == '__main__':
    unittest.main()
