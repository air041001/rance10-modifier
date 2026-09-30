import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import character_data
import training
import engine
import settings


class TrainingTests(unittest.TestCase):
    def test_upgrade_thresholds_from_verified_save_and_game_limit(self):
        for star, exp in [(10, 259), (37, 3400), (38, 3740), (39, 4114), (60, 30448), (100, 99999), (200, 99999)]:
            self.assertEqual(training.next_exp(star), exp)
        with self.assertRaises(ValueError):
            training.next_exp(-1)

    def test_story_maximum_stops_at_unavailable_stage(self):
        info = character_data.story(['条件成立', '条件成立', '条件不成立'], 2)
        self.assertEqual((info['maximum'], info['completed'], info['finished']), (2, 2, True))
        self.assertEqual(info['rows'][2]['state'], '无此故事')

    def test_story_condition_is_not_reported_as_satisfied(self):
        info = character_data.story(['条件成立', '条件成立', 'quest／実行済み'], 2)
        self.assertFalse(info['finished'])
        self.assertEqual(info['next_condition'], 'quest／実行済み')
        self.assertEqual(info['rows'][2]['state'], '未看过')

    def test_malformed_or_changed_metadata_rejected(self):
        with self.assertRaises(ValueError):
            character_data.parse('int 级别上限 = 200;')
        with self.assertRaises(ValueError):
            character_data.validate({'schema': 1, 'characters': {}})

    def test_training_rejects_destination_changed_before_prepare(self):
        with patch.object(engine, 'check_version'), patch.object(settings, 'save_dir', return_value=Path('expected')), patch.object(training, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, '目录'):
                training.apply(Path('other/LocalSave27.asd'), 'star', 'actor', 50, 'ignored')
            prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
