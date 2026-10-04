import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import app_paths
import settings


class ThemeSettingsTests(unittest.TestCase):
    def test_theme_and_paths_preserve_each_other(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'settings.json'
            initial = dict(game_dir='game', save_dir='saves', alice_path='component', theme='dark')
            with patch.object(app_paths, 'initialize'), patch.object(app_paths, 'CONFIG_FILE', file), \
                    patch.object(settings, '_current', initial):
                settings.save_theme('light')
                self.assertEqual(settings.load()['game_dir'], 'game')
                settings.save(Path(temp) / 'new-game', Path(temp) / 'new-save')
                self.assertEqual(settings.load()['theme'], 'light')
                self.assertEqual(json.loads(file.read_text(encoding='utf-8'))['theme'], 'light')


if __name__ == '__main__':
    unittest.main()
