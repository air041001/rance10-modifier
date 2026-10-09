"""Installations may change file identity, member order and VM symbol indices."""
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import app_paths
import assets
import live_profile
import settings


def integer(value):
    return struct.pack('<i', value)


def typ(value):
    return struct.pack('<iii', *value[:3]) + (typ(value[3]) if value[2] else b'')


def text(value):
    return value.encode('ascii') + b'\0'


def metadata():
    names = live_profile.REQUIRED
    indices = {name: i for i, name in enumerate(names)}
    refs = {('Character', '<FoodTicketEvent>'): 'FoodTicketEvent',
            ('CharacterCollection', 'm_character'): 'Character',
            ('PlayerCardCollection', 'm_org'): 'OrganizationCardCollection',
            ('OrganizationCardCollection', 'm_card'): 'PlayerCard'}
    structures = []
    for name in names:
        members = []
        for i, (datatype, field) in enumerate(live_profile.SCHEMAS[name]):
            target = indices.get(refs.get((name, field)), -1)
            child = (13, target, 0, None) if datatype == 79 else None
            members.append(dict(name=field or ('opaque' + str(i)),
                type=(datatype, target, int(child is not None), child)))
        structures.append(dict(index=indices[name], name=name, members=members))
    globals_ = [dict(index=0, name='other', type=(10, -1, 0, None))]
    for key, name in live_profile.GLOBALS.items():
        target = dict(PlayerGlobal='PlayerCommonParam', BonusGlobal='PartyBonusSwitcher',
                      CharacterGlobal='CharacterCollection', CardGlobal='PlayerCardCollection')[key]
        globals_.append(dict(index=len(globals_), name=name, type=(13, indices[target], 0, None)))
    return dict(code=b'\x00\x00' + integer(0) + b'\x2f\x00', globals=globals_, structures=structures,
                functions=[dict(index=0, name='Example', address=0, returned=(10, -1, 0, None), argc=0, variables=[])])


def container(ain):
    data = b'VERS' + integer(11) + b'CODE' + integer(len(ain['code'])) + ain['code']
    data += b'FUNC' + integer(len(ain['functions']))
    for f in ain['functions']:
        data += integer(f['address']) + text(f['name']) + typ(f['returned'])
        data += integer(f['argc']) + integer(len(f['variables'])) + integer(0) + integer(0)
        for v in f['variables']:
            data += text(v['name']) + typ(v['type']) + integer(0)
    data += b'GLOB' + integer(len(ain['globals']))
    for g in ain['globals']:
        data += text(g['name']) + typ(g['type']) + integer(0)
    data += b'STRT' + integer(len(ain['structures']))
    for s in ain['structures']:
        data += text(s['name']) + integer(0) + integer(-1) + integer(-1) + integer(len(s['members']))
        for m in s['members']:
            data += text(m['name']) + typ(m['type']) + integer(0)
    compressed = zlib.compress(data)
    return b'AI2\0\0\0\0\0' + struct.pack('<II', len(data), len(compressed)) + compressed


class LiveProfileTests(unittest.TestCase):
    def test_optional_chapter_display_maps_names_after_reordering(self):
        ain = metadata()
        index = len(ain['structures'])
        ain['structures'].append(dict(index=index, name='GameContext', members=[
            dict(name='extra', type=(10, -1, 0, None)),
            dict(name='m_chapter', type=(92, 74, 0, None))]))
        ain['globals'].insert(1, dict(index=1, name='g_gameContext', type=(13, index, 0, None)))
        for i, g in enumerate(ain['globals']):
            g['index'] = i
        data = live_profile.describe(ain, include_food=False)
        self.assertEqual(data['GameGlobal'], 1)
        self.assertEqual(data['Fields']['GameContext'], [1])
        ain['structures'][-1]['members'].reverse()
        ain['globals'].reverse()
        for i, g in enumerate(ain['globals']):
            g['index'] = i
        changed = live_profile.describe(ain, include_food=False)
        self.assertEqual(changed['Fields']['GameContext'], [0])
        self.assertNotEqual(changed['GameGlobal'], data['GameGlobal'])

    def test_unknown_chapter_metadata_does_not_gate_live_resources(self):
        ain = metadata()
        baseline = live_profile.describe(ain, include_food=False)
        self.assertEqual(baseline['GameGlobal'], -1)
        ain['structures'].append(dict(index=len(ain['structures']), name='GameContext', members=[
            dict(name='m_chapter', type=(12, -1, 0, None))]))
        changed = live_profile.describe(ain, include_food=False)
        self.assertEqual(changed['Fields']['PlayerCommonParam'], baseline['Fields']['PlayerCommonParam'])
        self.assertEqual(changed['GameGlobal'], -1)

    def test_member_and_global_reordering_maps_actual_positions(self):
        ain = metadata()
        baseline = live_profile.describe(ain)
        for s in ain['structures']:
            s['members'].reverse()
            s['members'].insert(0, dict(name='patchExtra', type=(10, -1, 0, None)))
        ain['globals'].reverse()
        for i, g in enumerate(ain['globals']):
            g['index'] = i
        changed = live_profile.describe(ain)
        self.assertNotEqual(changed['PlayerGlobal'], baseline['PlayerGlobal'])
        for name, expected in [('PlayerCommonParam', 'm_foodTicket'), ('PlayerCommonParam', 'm_friendPoint'),
                               ('PartyBonusSwitcher', 'm_maxPoint')]:
            s = next(s for s in ain['structures'] if s['name'] == name)
            position = next(i for i, m in enumerate(s['members']) if m['name'] == expected)
            slot = next(i for i, (_, field) in enumerate(live_profile.SCHEMAS[name]) if field == expected)
            self.assertEqual(changed['Fields'][name][slot], position)
            self.assertEqual(changed['Counts'][name], len(s['members']))

    def test_wrong_story_reference_does_not_disable_numeric_metadata(self):
        ain = metadata()
        character = next(s for s in ain['structures'] if s['name'] == 'Character')
        member = next(m for m in character['members'] if m['name'] == '<FoodTicketEvent>')
        member['type'] = (13, 0, 0, None)
        live_profile.describe(ain, include_food=False)
        with self.assertRaisesRegex(ValueError, '对象引用'):
            live_profile.describe(ain)

    def test_unknown_executable_identity_and_damaged_cache_are_supported(self):
        with tempfile.TemporaryDirectory(prefix='other-installation-') as directory:
            root = Path(directory)
            game = root / '另一位玩家的安装'
            game.mkdir()
            (game / 'Rance10.exe').write_bytes(b'non-baseline executable')
            (game / 'Rance10.ain').write_bytes(container(metadata()))
            with patch.object(app_paths, 'CACHE_DIR', root / 'cache'), patch.object(app_paths, 'CATALOG_FILE', root / 'absent.json'):
                file, descriptor = live_profile.prepare(game)
                self.assertEqual(descriptor['Fields']['PlayerCommonParam'][0], 0)
                self.assertIsNone(descriptor['Food'])
                self.assertIsNone(descriptor['Battle'])
                self.assertIn('战果', descriptor['BattleError'])
                self.assertIn('筛选入口', descriptor['FoodError'])
                file.write_text('{}', encoding='utf-8')
                self.assertEqual(live_profile.prepare(game)[1], descriptor)
                (game / 'Rance10.exe').write_bytes(b'another executable/translation')
                other, updated = live_profile.prepare(game)
                self.assertNotEqual(file, other)
                self.assertNotEqual(descriptor['ExeHash'], updated['ExeHash'])
                self.assertEqual(descriptor['Fields'], updated['Fields'])

    def test_corrupt_compression_is_reported(self):
        raw = bytearray(container(metadata()))
        raw[16:] = bytes(len(raw) - 16)
        with self.assertRaisesRegex(ValueError, '压缩数据'):
            live_profile.parse_ain(raw)

    def test_predicate_resolves_relocated_globals_and_method_indices(self):
        def fixture(start, global_index, method, function_index):
            code = (struct.pack('<HHiHH iHiHH i', 4, 0, global_index, 2, 0, method, 92, 0, 47, 126, function_index))
            function = dict(index=function_index, name='predicate', address=start)
            ain = dict(code=bytes(start) + code, globals=[dict(index=global_index, name='g_character')],
                       functions=[function, dict(index=method, name='CharacterCollection@Get')])
            return live_profile.predicate(ain, function)
        self.assertEqual(fixture(0, 1, 1501, 2001), fixture(100, 5, 1907, 2104))

    def test_game_save_directory_matches_ini_without_replacing_custom_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cn = root / 'AliceSoft/兰斯10/SaveData'
            jp = root / 'AliceSoft/ランス１０/SaveData'
            cn.mkdir(parents=True)
            jp.mkdir(parents=True)
            game = root / 'somewhere'
            game.mkdir()
            (game / 'AliceStart.ini').write_bytes('GameName = "ランス１０"\nSaveFolder = "SaveData"'.encode('cp932'))
            with patch.object(app_paths, 'documents_dir', return_value=root):
                self.assertEqual(app_paths.default_save_dir(game), jp)
                with patch.object(settings, 'load', return_value={'game_dir': str(game)}):
                    self.assertEqual(settings.save_dir(), jp)
                custom = root / 'my saves'
                with patch.object(settings, 'load', return_value={'game_dir': str(game), 'save_dir': str(custom)}):
                    self.assertEqual(settings.save_dir(), custom)

    def test_translated_text_can_use_original_archive_paths(self):
        art = {'カード／アイテム／my-cg.ajp': {}, '卡牌／my-cg.ajp': {}}
        self.assertEqual(assets.card_asset(art, 'my-cg', True), 'カード／アイテム／my-cg.ajp')
        self.assertEqual(assets.card_asset(art, 'my-cg'), '卡牌／my-cg.ajp')
        frames = ['シス／カード／%s／リーザス所属／アイテム.ajp' % part for part in ['下地', '枠']]
        self.assertEqual(assets.frame_assets(dict.fromkeys(frames), '利萨斯', True), frames)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows native component')
    def test_native_type_detection_survives_rtti_and_image_relocation(self):
        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'harness.exe'
            built = subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64',
                '/out:' + str(executable), '/r:System.Web.Extensions.dll', '/r:System.Core.dll', '/main:Harness',
                str(root / 'native/RuntimeProfile.cs'), str(root / 'tests/native_profile_harness.cs')],
                capture_output=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stdout.decode(errors='replace'))
            result = subprocess.run([str(executable)], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual(result.stdout.count(b'PASS '), 7)


if __name__ == '__main__':
    unittest.main()
