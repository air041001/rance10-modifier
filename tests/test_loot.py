"""Execute the injected AIN code with mutable strings and table/stock fixtures."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import loot_code
import live_profile

P = dict(TableString=1, IdString=2, EmptyString=0, Height=101, ReadString=102,
         GetColumn=[22, 26, -1], Realloc=[5, 1, 12], Owned=103, Stock=104, CardGlobal=12)


class String:
    def __init__(self, value=''):
        self.value = value


def card(ident, chapter, deleted=0):
    return {'Id': ident, '识别名': 'same-person', '所属': 1, '種別': 10, '出现': chapter,
            '削除': deleted, '技能１': 0, '技能２': 0}


CATALOG = dict(cards=[card('A1', 1), card('A2', 1), card('B1', 2), card('special', 3),
                       card('removed', 1, 1), card('测试dummy', 1)], skills=[])


def evaluate(pool, chapter=1, all_cards=False, unique=False, owned=(), stock=(), table_size=None, physical=False):
    code = loot_code.Code()
    loot_code.insert(code, P, chapter, CATALOG if all_cards else None, all_cards, unique)
    code.op(47)
    raw = code.finish(0)
    instructions = {at: (op, args) for at, op, args in loot_code.decode(raw, 0, len(raw))}
    array = [String()] + [String(v) for v in pool]
    local = {i: 0 for i in range(12)}
    local.update({5: String(), 6: String(), 7: array, 8: len(pool)})
    stack, pos, steps = [], 0, 0
    def pop_args(count):
        result = stack[-count:]
        del stack[-count:]
        return result
    while True:
        steps += 1
        assert steps < 20000, 'Candidate loop did not terminate'
        op, args = instructions[pos]
        pos += 2+len(args)*4
        if op == 0: stack.append(args[0])
        elif op == 1: stack.pop()
        elif op == 5: stack.append(local)
        elif op == 4: stack.append({P['CardGlobal']: 'player'})
        elif op == 65: stack.append(String({0: '', 1: 'cards', 2: 'Id'}[args[0]]))
        elif op == 2:
            page, index = pop_args(2)
            stack.append(page[index])
        elif op == 25:
            page, index, value = pop_args(3)
            page[index] = value
            stack.append(value)
        elif op == 41: stack.extend(stack[-2:])
        elif op == 49:
            page, index = pop_args(2)
            page[index] += 1
        elif op == 102: stack[-2:] = stack[-2:][::-1]
        elif op == 68:
            target, source = pop_args(2)
            assert isinstance(target, String) and isinstance(source, String)
            target.value = source.value
            stack.append(String(source.value))
        elif op == 119: stack.pop()
        elif op == 121:
            source = stack.pop()
            assert isinstance(source, String)
            stack.append(String(source.value))
        elif op in (9, 21, 22, 24):
            a, b = pop_args(2)
            stack.append({9: lambda: a+b, 21: lambda: a<=b, 22: lambda: a>=b, 24: lambda: a==b}[op]())
        elif op == 44: pos = args[0]
        elif op in (45, 46):
            value = stack.pop()
            if bool(value) == (op == 46): pos = args[0]
        elif op == 90:
            if args == P['GetColumn']:
                name, field, file = pop_args(3)
                assert name.value == 'cards' and field.value == 'Id' and file == 0
                stack.append(0)
            elif args == P['Realloc']:
                target, length = pop_args(2)
                del target[length:]
                target.extend(String() for _ in range(max(0, length-len(target))))
            else: raise AssertionError(args)
        elif op == 48:
            if args[0] == P['Height']:
                name, file = pop_args(2)
                stack.append(len(CATALOG['cards']) if table_size is None else table_size)
            elif args[0] == P['ReadString']:
                name, column, row, default, file = pop_args(5)
                assert column == 0 and name.value == 'cards' and file == 0
                stack.append(String(CATALOG['cards'][row]['Id']))
            elif args[0] == P['Owned']:
                stack.append(stack.pop().value in owned)
            else: raise AssertionError(args)
        elif op == 92:
            value = stack.pop(); method = stack.pop(); player = stack.pop()
            assert args == [1] and method == P['Stock'] and player == 'player'
            stack.append(0 if value.value in stock else -1)
        elif op == 47:
            assert not stack, 'Injected code left operands on the game stack'
            result = ([v.value for v in array[1:local[8]+1]], steps)
            return result + ([v.value for v in array],) if physical else result
        else: raise AssertionError(op)


class LootTests(unittest.TestCase):
    def test_patch_uses_retail_vm_instructions_without_shorthand_refs(self):
        import hashlib
        builder = loot_code.Code()
        for _ in range(300):
            builder.op(5); builder.op(0, 8)
            for op in (41, 2, 42, 1, 49, 1): builder.op(op)
        first = len(builder.data)
        builder.op(0, 0); builder.op(47)
        second = len(builder.data)
        builder.op(0, 0); builder.op(47)
        source = builder.finish(0)
        offset = 5000
        profile = dict(P, Offset=offset, Length=len(source),
                       SpanHash=hashlib.sha256(source).hexdigest(),
                       Chapter1Site=offset+first, Chapter2Site=offset+second)
        for all_cards, unique in ((False, True), (True, False), (True, True)):
            patch = loot_code.make_code(source, {'Loot': profile}, CATALOG, all_cards, unique)
            rows = loot_code.decode(patch, 0, len(patch))
            self.assertFalse({93, 94} & {op for _, op, _ in rows})
            positions = {offset+at for at, _, _ in rows}
            self.assertTrue(all(args[0] in positions for _, op, args in rows if op in loot_code.BRANCHES))

    def test_discarded_postfix_increment_keeps_page_index_and_value(self):
        builder = loot_code.Code()
        builder.op(5); builder.op(0, 8)
        for op in (41, 2, 42, 1, 49, 1): builder.op(op)
        raw = builder.finish(0)
        rows = loot_code.decode(raw, 0, len(raw))
        consumed, op, args = loot_code.compact(rows, 2, set())
        self.assertEqual((consumed, op, args), (6, 49, []))
        for protected in rows[3:]:
            self.assertEqual(loot_code.compact(rows, 2, {protected[0]}), (1, 41, []))
        # Both sequences discard the postfix result; only the referenced int changes.
        for ops in ((41, 2, 42, 1, 49, 1), (op,)):
            page = {8: 12, 9: 99}
            stack = [page, 8]
            for command in ops:
                if command == 41: stack.extend(stack[-2:])
                elif command == 2:
                    index = stack.pop(); stack.append(stack.pop()[index])
                elif command == 42:
                    a, b, c = stack[-3:]; stack[-3:] = [c, a, b, c]
                elif command == 1: stack.pop()
                elif command == 49:
                    index = stack.pop(); stack.pop()[index] += 1
            self.assertEqual(page, {8: 13, 9: 99})
            self.assertEqual(stack, [])

    def test_redundant_if_branch_keeps_both_outcomes_and_incoming_targets(self):
        for op in (45, 46):
            rows = [(0, op, [12]), (6, 44, [40]), (12, 0, [1])]
            consumed, inverse, args = loot_code.compact(rows, 0, set())
            self.assertEqual((consumed, inverse, args), (2, 91-op, [40]))
            for condition in (False, True):
                original = 12 if condition == (op == 46) else 40
                changed = 40 if condition == (inverse == 46) else 12
                self.assertEqual(original, changed)
            self.assertEqual(loot_code.compact(rows, 0, {6}), (1, op, [12]))

    def test_full_pools_keep_chapters_separate(self):
        first, _ = evaluate(['old1', 'old2'], all_cards=True)
        second, _ = evaluate(['old1', 'old2'], chapter=2, all_cards=True)
        self.assertEqual(first, ['A1', 'A2', 'special'])
        self.assertEqual(second, ['B1'])

    def test_versions_and_pending_cards_are_filtered(self):
        pool, _ = evaluate(['A1', 'A2', 'special'], unique=True, owned={'A1'}, stock={'special'})
        self.assertEqual(pool, ['A2'])

    def test_both_switches_combine_without_deleted_or_debug_cards(self):
        pool, _ = evaluate(['old1', 'old2'], all_cards=True, unique=True, owned={'A1'}, stock={'special'})
        self.assertEqual(pool, ['A2'])

    def test_all_owned_restores_original_pool_and_terminates(self):
        original = ['old1', 'old2']
        result, steps = evaluate(original, all_cards=True, unique=True, owned={'A1', 'A2', 'special'})
        self.assertEqual(result, original)
        self.assertLess(steps, 1000)
        self.assertEqual(evaluate(original, unique=True, owned=set(original))[0], original)

    def test_one_entry_random_pool_still_expands_and_excludes_owned_version(self):
        self.assertEqual(evaluate(['A1'], all_cards=True, unique=True, owned={'A1'})[0], ['A2', 'special'])
        self.assertEqual(evaluate(['A1'], all_cards=True)[0], ['A1', 'A2', 'special'])

    def test_single_random_candidate_without_any_new_option_uses_fallback(self):
        self.assertEqual(evaluate(['A1'], unique=True, owned={'A1'})[0], ['A1'])

    def test_running_table_mismatch_keeps_original_pool(self):
        self.assertEqual(evaluate(['old1', 'old2'], all_cards=True, table_size=20)[0], ['old1', 'old2'])

    def test_original_duplicate_weights_survive_filtering(self):
        result, _ = evaluate(['A1', 'A2', 'A2'], unique=True, owned={'A1'})
        self.assertEqual(result, ['A2', 'A2'])

    def test_later_bonus_cannot_see_rejected_or_appended_source_entries(self):
        result, _, physical = evaluate(['old1', 'old2'], all_cards=True, unique=True,
                                       owned={'A1'}, stock={'special'}, physical=True)
        self.assertEqual(result, ['A2'])
        self.assertEqual([value for value in physical if value], result)
        self.assertGreaterEqual(len(physical), 3)

    def test_special_second_part_versions_and_shared_items(self):
        cards = {'cards': CATALOG['cards'] + [card('second-special', 3)], 'skills': []}
        profile = dict(Chapter1Ids=['special'], Chapter2Ids=['second-special', 'A1'])
        first = [cards['cards'][i]['Id'] for i in loot_code.eligible_rows(cards, 1, profile)]
        second = [cards['cards'][i]['Id'] for i in loot_code.eligible_rows(cards, 2, profile)]
        self.assertIn('special', first)
        self.assertNotIn('second-special', first)
        self.assertIn('second-special', second)
        self.assertIn('A1', second)  # An item which the original Chapter2 box already contains.
        self.assertNotIn('A2', second)

    def test_empty_original_pool_can_be_expanded(self):
        self.assertEqual(evaluate([], chapter=2, all_cards=True)[0], ['B1'])

    def test_literal_table_is_bounded_by_following_metadata(self):
        import struct
        data = b'junkSTR0' + struct.pack('<i', 2) + b'\0card\0DELG' + struct.pack('<ii', 32, 1)
        self.assertEqual(live_profile.string_table(data, 0), ['', 'card'])
        with self.assertRaises(ValueError):
            live_profile.string_table(data[:-4], 0)


if __name__ == '__main__':
    unittest.main()
