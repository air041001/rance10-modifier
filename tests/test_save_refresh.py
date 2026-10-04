import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import engine


class SaveRefreshTests(unittest.TestCase):
    def test_file_removed_during_refresh_does_not_hide_other_saves(self):
        with tempfile.TemporaryDirectory() as temp:
            disappearing = Path(temp) / 'LocalSave1.asd'
            remaining = Path(temp) / 'LocalSave2.asd'
            disappearing.write_bytes(b'old')
            remaining.write_bytes(b'new')
            original = Path.read_bytes
            def read(path):
                if path == disappearing:
                    path.unlink()
                    raise FileNotFoundError(str(path))
                return original(path)
            with patch.object(Path, 'read_bytes', read), patch.object(engine, 'parse', return_value={}), \
                    patch.object(engine, 'metadata', return_value=dict(slot=2, time='now', comment='')), \
                    patch.object(engine, 'collection', return_value=(None, None, {})):
                rows = engine.list_saves(temp)
            self.assertEqual([r['slot'] for r in rows], [2])
            self.assertTrue(remaining.is_file())


if __name__ == '__main__':
    unittest.main()
