"""Exercise whole-version removal and the possession graph through real v8 bytes."""
from pathlib import Path
import copy
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import card_removal
import engine
import save_compat
import settings
import character_data


def fixture(encoding='gbk'):
    s = dict(defs=[dict(name=name, fields=fields) for name, fields in save_compat.SCHEMAS.items()],
             records=[], arrays=[], strings=[], extra_strings=[], kv=[], encoding=encoding)
    def arr(typ, values):
        index = len(s['arrays'])
        s['arrays'].append(dict(rank=1, dims=[len(values)], flat=[dict(type=typ, values=values)]))
        return index
    def rec(name, **values):
        sid = next(i for i, d in enumerate(s['defs']) if d['name'] == name)
        indices = []
        for typ, key in s['defs'][sid]['fields']:
            indices.append(len(s['kv']))
            s['kv'].append(values.get(key, -1 if typ == 13 else 0))
        ref = len(s['records'])
        s['records'].append(dict(sid=sid, kv=indices))
        return ref
    def string(value):
        return engine.addstr(s, value)
    hero, other = ('甲', '乙') if encoding == 'gbk' else ('アギレダ', 'シィル')
    ids = ['Lv1 ' + hero, 'Lv2 ' + hero, 'Lv3 ' + other]
    table = [dict(Id=ident, 识别名=hero if i < 2 else other, 所属=1, 種別=0) for i, ident in enumerate(ids)]
    cards = [rec('PlayerCard', **{'<Id>': string(ident), 'Index': i + 10, 'SortedIndex': 12-i,
            'UniqueId': 100+i, 'm_count': 5 if i == 0 else 1, 'm_skill': arr(13, [])}) for i, ident in enumerate(ids)]
    events, characters = [], []
    for name in [hero, other]:
        event = rec('FoodTicketEvent', m_id=string(name), m_eventStage=2, m_exBaseKey=string('story.' + name))
        replay = rec('CharacterEventCollection', **{'<Id>': string(name), 'm_key': string('replay.' + name)})
        events.append(event)
        characters.append(rec('Character', **{'m_id': string(name), 'm_star': 80, '<Exp>': 123,
                           '<NextExp>': 999, '<ReplayEvent>': replay, '<FoodTicketEvent>': event}))
    character_pool = arr(13, sorted(characters, key=lambda ref: s['strings'][engine.fields(s, ref)['m_id']].encode(encoding)))
    character_root = rec('CharacterCollection', m_character=character_pool)
    join = '参战' if encoding == 'gbk' else '参戦'
    local_events = [hero + '／' + join, hero + '／キャライベントＡ', other + '／' + join, '１２３／抱' + hero]
    event_array = arr(12, [string(value) for value in local_events])
    event_root = rec('EventReadInfo', m_eventName=event_array)
    common = rec('PlayerCommonParam', m_bestFriendId=string(hero), m_foodTicket=3, **{'<ItemStar>': 20})
    context = rec('GameContext', m_shownCardIds=arr(12, [string(ident) for ident in ids]))
    bonus = rec('ClearPointBonusCollection', m_bonus=arr(13, [rec('ClearPointBonus', **{'<IsUse>': 1, '<Type>': 3, '<Value>': 5})]))
    orgs = []
    for i in range(10):
        refs = sorted(cards, key=lambda ref: s['strings'][engine.fields(s, ref)['<Id>']].encode(encoding)) if i == 0 else []
        orgs.append(rec('OrganizationCardCollection', m_card=arr(13, refs),
            m_characterId=arr(12, [string(name) for name in sorted([hero, other], key=lambda name: name.encode(encoding))] if i == 0 else []),
            m_uniqueId=103))
    root = rec('PlayerCardCollection', m_org=arr(13, orgs), m_stock=arr(13, []), m_extraCard=arr(13, []), m_card=arr(13, []))
    leader = rec('LeaderCard', **{'m_cardId': string(ids[0]), '<CharacterId>': string(hero),
        '<OrganizationId>': 1, 'm_status': rec('CommonStatus', **{'<Atk>': 900, 'StatusMaxPer': 100}),
        'm_state': rec('LeaderState', m_state=2, IsCritical=1), 'm_hp': 1000,
        'm_skillCounter': rec('SkillCounterValueCollection', m_cardId=string(ids[0]),
            m_counter=arr(13, [rec('SkillCounterValue', UsedCount=2, IsUsed=1)])), '': arr(21, [-1, -1])})
    party = rec('Party', m_stockCardId=arr(12, [string(ids[0]), string(ids[2])]),
                m_preBattleCardIds=arr(12, [string(ids[0]), card_removal.EMPTY_STRING]))
    s['globals'] = {'g_playerCard': (13, root), 'g_party': (13, party), 'g_character': (13, character_root),
                    'g_eventInfo': (13, event_root), 'g_playerCommonParam': (13, common),
                    'g_gameContext': (13, context), 'g_clearPointBonus': (13, bonus), 'unrelated_flag': (10, 77)}
    return s, table, dict(ids=ids, hero=hero, other=other, orgs=orgs, cards=cards, root=root,
                         leader=leader, party=party, characters=characters, events=events,
                         character_pool=character_pool, event_array=event_array, local_events=local_events,
                         common=common, context=context)


def serialize(s):
    p = engine.pack
    out, header = bytearray(b'rance10\0' + b'\0' * 60), [0, 8, 64, 0] + [0] * 10
    header[4], header[5] = len(out), len(s['records'])
    for row in s['records']:
        out += p(row['sid'], len(row['kv']), *row['kv'])
    header[6], header[7] = len(out), len(s['globals'])
    for name, (typ, value) in s['globals'].items():
        out += p(typ, value) + name.encode(s['encoding']) + b'\0'
    header[8], header[9] = len(out), len(s['strings'])
    out += b''.join(value.encode(s['encoding']) + b'\0' for value in s['strings'])
    header[10], header[11] = len(out), len(s['arrays'])
    out += b''.join(engine.array_bytes(row) for row in s['arrays'])
    header[12], header[13] = len(out), len(s['kv'])
    out += p(*s['kv']) + p(len(s['defs']))
    for definition in s['defs']:
        out += definition['name'].encode() + b'\0' + p(len(definition['fields']))
        for typ, name in definition['fields']:
            out += p(typ) + name.encode() + b'\0'
    footer = len(out)
    meta = b'99|x|x|x|x|2026/10/14 12:00:00|fixture'
    out += p(len(meta)) + meta
    struct.pack_into('<14i', out, 8, *header)
    struct.pack_into('<i', out, 64, footer)
    return b'GD\x01\x01' + p(len(out)) + zlib.compress(out)


class CardRemovalTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='rance-delete-')
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'LocalSave99.asd'
        self.s, self.table, self.refs = fixture()
        self.path.write_bytes(serialize(self.s))
        self.raw = self.path.read_bytes()
        for mock in [patch.object(engine, 'catalog_data', side_effect=lambda: dict(cards=self.table)),
                     patch.object(save_compat, 'rules', return_value=dict(cards=True, characters=True)),
                     patch.object(save_compat, 'verify_source'), patch.object(save_compat, 'encoding', return_value='gbk'),
                     patch.object(settings, 'save_dir', return_value=self.path.parent)]:
            mock.start()
            self.addCleanup(mock.stop)

    def remove(self, ids):
        output, report = card_removal.prepare(self.path, ids, engine.sha(self.path.read_bytes()))
        return engine.parse(output, str(self.path)), report

    def test_whole_version_removes_all_copies_but_other_variant_keeps_character(self):
        after, report = self.remove([self.refs['ids'][0]])
        org = engine.fields(after, self.refs['orgs'][0])
        names = [engine.text(after, value) for value in engine.flat(after, org['m_characterId'], 12)]
        self.assertIn(self.refs['hero'], names)
        self.assertEqual(report['cards'][0]['copies'], 5)
        self.assertEqual(report['removed_characters'], [])
        self.assertEqual(set(engine.collection(after)[2]), set(self.refs['ids'][1:]))
        self.assertEqual(engine.fields(after, self.refs['characters'][0])['m_star'], 80)
        self.assertEqual(engine.fields(after, self.refs['events'][0])['m_eventStage'], 2)
        self.assertEqual([engine.text(after, value) for value in engine.flat(after, self.refs['event_array'], 12)], self.refs['local_events'])
        self.assertEqual(self.path.read_bytes(), self.raw)

    def test_last_version_removes_character_and_its_local_progress(self):
        before = engine.parse(self.raw, str(self.path))
        after, report = self.remove(self.refs['ids'][:2])
        org = engine.fields(after, self.refs['orgs'][0])
        self.assertEqual([engine.text(after, value) for value in engine.flat(after, org['m_characterId'], 12)], [self.refs['other']])
        self.assertEqual(report['removed_characters'], [self.refs['hero']])
        for ref in [self.refs['characters'][1], self.refs['events'][1]]:
            self.assertEqual(engine.fields(after, ref), engine.fields(before, ref))
        self.assertNotIn(self.refs['hero'], engine.collection(after)[3])
        self.assertEqual(engine.fields(after, self.refs['characters'][0])['m_star'], 0)
        self.assertEqual(engine.fields(after, self.refs['events'][0])['m_eventStage'], 0)
        self.assertEqual([engine.text(after, value) for value in engine.flat(after, self.refs['event_array'], 12)], self.refs['local_events'][2:])
        self.assertEqual(report['removed_personal_events'], self.refs['local_events'][:2])
        common = engine.fields(after, self.refs['common'])
        self.assertEqual(card_removal.string(after, common['m_bestFriendId']), '')
        self.assertEqual((common['m_foodTicket'], common['<ItemStar>']), (3, 20))
        shown = engine.fields(after, self.refs['context'])['m_shownCardIds']
        self.assertEqual([engine.text(after, value) for value in engine.flat(after, shown, 12)], [self.refs['ids'][2]])
        self.assertEqual(after['globals']['unrelated_flag'], (10, 77))
        self.assertEqual(engine.metadata(before)['raw'], engine.metadata(after)['raw'])

    def test_reacquisition_creates_fresh_character_without_reusing_orphan_record(self):
        after, _ = self.remove(self.refs['ids'][:2])
        original = copy.deepcopy(after)
        chars = engine.collection(after)[3]
        data = dict(rules=dict(event_paths=dict(character_root='识别名情报', event_leaf='事件')))
        with patch.object(character_data, 'load', return_value=dict(star_cap=200, character_root='识别名情报')):
            ref, values = engine.ensure_character(after, self.refs['hero'], chars, set(), data)
        self.assertNotEqual(ref, self.refs['characters'][0])
        self.assertEqual((values['m_star'], values['<Exp>']), (5, 0))
        self.assertEqual(engine.fields(after, values['<FoodTicketEvent>'])['m_eventStage'], 0)
        payload = engine.build_payload(after, original)
        check = engine.parse(b'GD\x01\x01' + engine.pack(len(payload)) + zlib.compress(payload), str(self.path))
        self.assertEqual(engine.collection(check)[3][self.refs['hero']][0], ref)

    def test_empty_local_event_array_does_not_require_a_named_character_or_event(self):
        self.s['arrays'][self.refs['event_array']] = dict(rank=-1, dims=[], flat=[])
        self.path.write_bytes(serialize(self.s))
        after, report = self.remove(self.refs['ids'][:2])
        self.assertNotIn(self.refs['hero'], engine.collection(after)[3])
        self.assertEqual(report['removed_personal_events'], [])

    def test_unsets_leader_and_saved_party_without_shifting_slot_positions(self):
        after, report = self.remove([self.refs['ids'][0]])
        leader = engine.fields(after, self.refs['leader'])
        self.assertEqual(card_removal.string(after, leader['m_cardId']), '')
        self.assertEqual((leader['<OrganizationId>'], leader['m_hp']), (-1, 0))
        status = engine.fields(after, leader['m_status'])
        self.assertEqual(status['<Atk>'], 0)
        self.assertEqual(status['StatusMaxPer'], 100)
        self.assertEqual(after['arrays'][leader['']]['rank'], -1)
        party = engine.fields(after, self.refs['party'])
        self.assertEqual([card_removal.string(after, value) for value in engine.flat(after, party['m_stockCardId'], 12)], ['', self.refs['ids'][2]])
        self.assertEqual(len(report['unset_leaders']), 1)
        remaining = engine.collection(after)[2]
        self.assertEqual([engine.fields(after, remaining[ident][1])['Index'] for ident in self.refs['ids'][1:]], [0, 1])

    def test_rejects_unowned_duplicate_or_pending_selection(self):
        for ids in [['absent'], [self.refs['ids'][0]] * 2, []]:
            with self.assertRaises(ValueError):
                self.remove(ids)
        root = engine.fields(self.s, self.refs['root'])
        self.s['arrays'][root['m_stock']]['flat'][0]['values'] = [self.refs['cards'][0]]
        engine.resize(self.s, root['m_stock'])
        self.path.write_bytes(serialize(self.s))
        with self.assertRaisesRegex(ValueError, '未处理'):
            self.remove([self.refs['ids'][0]])

    def test_apply_backs_up_exact_original_and_rejects_stale_selection(self):
        report = card_removal.apply(self.path, [self.refs['ids'][0]], engine.sha(self.raw), self.path.parent / 'backup')
        self.assertTrue(report['installed'])
        self.assertEqual((Path(report['backup']) / self.path.name).read_bytes(), self.raw)
        with self.assertRaisesRegex(ValueError, '更新'):
            card_removal.apply(self.path, [self.refs['ids'][1]], engine.sha(self.raw))

    def test_cp932_and_absent_specific_characters_are_supported(self):
        s, table, refs = fixture('cp932')
        self.path.write_bytes(serialize(s))
        self.table = table
        with patch.object(save_compat, 'encoding', return_value='cp932'):
            after, report = self.remove(refs['ids'][:2])
        self.assertEqual(report['removed_characters'], [refs['hero']])
        self.assertEqual(set(engine.collection(after)[2]), {refs['ids'][2]})

    def test_same_character_selection_uses_current_ownership_and_excludes_items(self):
        rows = [dict(id='a', character='actor', kind='人物', owned=True),
                dict(id='b', character='actor', kind='人物', owned=True),
                dict(id='c', character='actor', kind='人物', owned=False),
                dict(id='item', character='actor', kind='物品', owned=True)]
        context = dict(cards=rows)
        self.assertEqual(card_removal.same_character(context, 'a'), ['a', 'b'])
        self.assertEqual(card_removal.same_character(context, 'item'), [])
        self.assertEqual(card_removal.same_character(context, None), [])


if __name__ == '__main__':
    unittest.main()
