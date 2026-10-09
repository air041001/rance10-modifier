"""Country arguments must reach only battle actions, before opening a process."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import app_paths
import runtime


class BattleRuntimeTests(unittest.TestCase):
    def test_country_and_delta_rejected_before_connection(self):
        with patch.object(runtime.engine, 'check_live_version') as connect:
            for action, amount, country in [('addbattle', 1, None), ('addbattle', 1, 0),
                    ('addbattle', 1, 5), ('addbattle', 1, True), ('addbattle', 0, 2),
                    ('addbattle', 2, 2), ('addbattle', True, 2), ('fillbattle3', None, '2'),
                    ('fillfriend3', None, 2)]:
                with self.subTest(action=action, amount=amount, country=country):
                    with self.assertRaises(ValueError):
                        runtime.run(action, amount, country)
            connect.assert_not_called()

    def test_battle_actions_forward_country_and_log_before_after(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'operations.jsonl'
            with patch.object(runtime.engine, 'check_live_version', return_value=Path('profile.json')), \
                    patch.object(runtime.settings, 'game_dir', return_value=Path('game')), \
                    patch.object(app_paths, 'LOG_FILE', log), patch.object(app_paths, 'initialize'), \
                    patch.object(runtime, '_invoke') as invoke:
                for action, amount in [('addbattle', -1), ('addbattle', 1), ('fillbattle3', None)]:
                    data = dict(success=True, action=action, battle_country=3, battle_before=[0, 0, 1, 0],
                                battle_points=[0, 0, 2, 0], food=3, friend_points=1, total_points=25)
                    invoke.return_value = data
                    self.assertEqual(runtime.run(action, amount, country=3), data)
                    args = invoke.call_args.args[0]
                    self.assertEqual(args[:1], ['--' + action])
                    self.assertEqual(args[args.index('--country') + 1], '3')
                    if amount is not None:
                        self.assertEqual(args[1], str(amount))
                rows = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
                self.assertEqual(len(rows), 3)
                self.assertTrue(all(row['battle_country'] == 3 for row in rows))


if __name__ == '__main__':
    unittest.main()
