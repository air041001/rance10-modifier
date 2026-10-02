"""Feature compatibility must neither reject a translation nor accept wrong field types."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import app_paths
import assets
import engine
import game_profile
import save_compat
import settings


def catalog_fixture():
    card = dict(Id='Lv1 リーザス', 識別名='リーザス', 所属=2, 種別=0, 発生=1, 削除=0, 裸=0,
        **{'ＣＧ名': 'image', 'ＳＲ': 0, 'ＨＰ': 100, 'ＡＴＫ': 100, 'スキル１': 1, 'スキル２': 0})
    skill = dict(Id=1, 名前='攻撃', 説明='説明', **{'ＡＰ': 1})
    skill.update({key + n: 0 for key in ['効果', '数値'] for n in '１２３'})
    def table(name, row):
        columns = ', '.join(('string' if isinstance(v, str) else 'int') + ' ' + k for k, v in row.items())
        values = ', '.join(json.dumps(v, ensure_ascii=False) for v in row.values())
        return 'table ' + name + ' = {\n { ' + columns + ' },\n { ' + values + ' },\n};\n'
    return table('カードデータ', card) + table('スキルデータ', skill)


def save_fixture():
    return dict(defs=[dict(name=n, fields=list(fields)) for n, fields in save_compat.SCHEMAS.items()])


class CompatibilityTests(unittest.TestCase):
    def test_unknown_executable_allows_directory_but_not_live_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder)
            for name in game_profile.GAME_HASHES:
                (game / name).write_bytes(b'other translation')
            self.assertEqual(engine.validate_game_directory(game), game)
            with patch.object(settings, 'game_dir', return_value=game):
                with self.assertRaisesRegex(ValueError, '实时修改'):
                    engine.check_live_version()

    def test_local_catalog_accepts_different_counts_and_japanese_fields(self):
        data = assets.parse_catalog(catalog_fixture())
        self.assertEqual(len(data['cards']), 1)
        self.assertEqual(data['cards'][0]['识别名'], 'リーザス')
        self.assertEqual(data['skills'][0]['名称'], '攻撃')
        self.assertEqual(data['cards'][0]['技能１'], 1)
        assets.validate_catalog(data, verify_source=False)
        duplicate = copy.deepcopy(data)
        duplicate['cards'].append(duplicate['cards'][0])
        duplicate['content_digest'] = game_profile.catalog_digest(duplicate)
        with self.assertRaisesRegex(ValueError, '结构'):
            assets.validate_catalog(duplicate, verify_source=False)

    def test_source_binding_rejects_old_cache_after_ex_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder)
            ex = game / 'Rance10EX.ex'
            ex.write_bytes(b'local card table')
            data = assets.parse_catalog(catalog_fixture())
            data['source'] = save_compat.source(game, 'CP932')
            with patch.object(settings, 'game_dir', return_value=game):
                assets.validate_catalog(data)
                ex.write_bytes(b'a different card table')
                with self.assertRaisesRegex(ValueError, '重新准备'):
                    assets.validate_catalog(data)

    def test_types_for_written_fields_are_checked(self):
        s = save_fixture()
        save_compat.validate_save(s, exact=['PlayerCard', 'PlayerCardSkill'], scope='cards')
        card = next(d for d in s['defs'] if d['name'] == 'PlayerCard')
        card['fields'] = [(12 if n == 'm_count' else t, n) for t, n in card['fields']]
        with self.assertRaisesRegex(ValueError, 'm_count'):
            save_compat.validate_save(s, exact=['PlayerCard'], scope='cards')

    def test_unrelated_field_change_does_not_disable_reading(self):
        s = save_fixture()
        org = next(d for d in s['defs'] if d['name'] == 'OrganizationCardCollection')
        org['fields'] = [(12 if n == 'm_uniqueId' else t, n) for t, n in org['fields']]
        save_compat.validate_save(s)
        with self.assertRaisesRegex(ValueError, 'm_uniqueId'):
            save_compat.validate_save(s, scope='card_write')

    def test_negative_record_indices_are_rejected(self):
        s = dict(defs=[dict(name='Example', fields=[(10, 'value')])],
                 records=[dict(sid=0, kv=[-1])], kv=[7])
        with self.assertRaisesRegex(ValueError, '越界'):
            engine.fields(s, 0)

    def test_cp932_strings_are_preserved_in_new_records(self):
        value = '識別名情報.リーザス.イベント'
        data = value.encode('cp932') + b'\0'
        self.assertEqual(engine.Reader(data, encoding='cp932').text(), value)
        s = dict(strings=[], extra_strings=[], encoding='cp932')
        self.assertEqual(engine.addstr(s, value), 0)
        self.assertEqual(s['extra_strings'], [data])
        self.assertEqual(engine.addstr(s, value), 0)

    def test_rule_check_rejects_empty_output_and_changed_constants(self):
        with self.assertRaisesRegex(ValueError, '未读到'):
            save_compat.normalize_code('', {})
        code = 'FUNC 1\nPUSH 100\nRETURN\nENDFUNC Example'
        self.assertNotEqual(save_compat.normalize_code(code, {}),
                            save_compat.normalize_code(code.replace('100', '101'), {}))

    def test_translation_and_address_changes_keep_same_rule(self):
        jp = 'FUNC 5\n0x100:\nS_PUSH "識別名情報.イベント"\nJUMP 0x100\nRETURN'
        zh = 'FUNC 6\n0x500:\nS_PUSH "识别名情报.事件"\nJUMP 0x500\nRETURN'
        self.assertEqual(save_compat.normalize_code(jp, {}), save_compat.normalize_code(zh, {}))

    def test_constructor_overloads_are_distinguished(self):
        symbols = save_compat.function_symbols('/* 0x01 */ void PlayerCard@0(void);\n'
            '/* 0x02 */ void PlayerCard@0(string id);')
        self.assertEqual(symbols, {1: 'PlayerCard@0', 2: 'PlayerCard@0#1'})
        self.assertIn('PlayerCard@0#1', save_compat.GROUPS['cards'])

    def test_rule_failure_disables_only_affected_feature(self):
        with patch.object(save_compat, 'rules', return_value=dict(cards=False, star=True, enhancement=True)):
            save_compat.require_rule({}, 'star')
            save_compat.require_rule({}, 'enhancement')
            with self.assertRaisesRegex(ValueError, '卡牌初始化'):
                save_compat.require_rule({}, 'cards')

    def test_ain_rule_dump_uses_names_not_numeric_indices(self):
        symbols = '/* 0x01 */ void Example(void);'
        def run(tool, args):
            if '--functions' in args:
                return symbols
            self.assertEqual(args[args.index('--function') + 1], 'Example')
            return 'FUNC 1\nPUSH 0\nRETURN'
        import save_rule_hashes
        expected = save_compat.normalize_code('FUNC 1\nPUSH 0\nRETURN', {})
        with patch.object(assets, '_run', side_effect=run), patch.object(save_compat, 'file_hash', return_value='ain'), \
             patch.object(save_compat, 'GROUPS', {'cards': ['Example']}), \
             patch.object(save_rule_hashes, 'EXPECTED', {'Example': [expected]}):
            self.assertEqual(save_compat.inspect_rules(Path('game'), Path('tool'), 'CP936')['groups'], {'cards': True})


if __name__ == '__main__':
    unittest.main()
