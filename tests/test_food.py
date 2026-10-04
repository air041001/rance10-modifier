"""Check predicate branches, reference ownership and stale helper replies."""
import json
import queue
import struct
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import food

PROFILE = dict(CharacterGlobal=11, Food=dict(Offset=0x1000, Length=368,
    FirstLength=114, SecondOffset=256, GetCharacter=1501, IsMax=1502))


def evaluate(code, *, card_character=42, finished=False, profile=PROFILE):
    """Small AIN stack fixture. Returned Character/FoodTicketEvent refs are owned.

    Implements the instructions used here, including the original double
    assignment and SP_INC transfer. Any leftover operand/ref fails the fixture.
    """
    names = {value: key for key, value in food.OPS.items()}
    arguments = {'PUSH': 1, 'IFZ': 1, 'CALLMETHOD': 1}
    local = {0: 'character-id', 1: -1, 2: -1}
    global_ = {profile['CharacterGlobal']: 200}
    refs = {card_character: 1, 300: 1}
    stack, pos, calls = [], 0, []

    def release(ref):
        if ref == -1:
            return
        refs[ref] -= 1
        assert refs[ref] >= 1, 'Borrowed reference was released'

    while pos < len(code):
        name = names[struct.unpack_from('<H', code, pos)[0]]
        pos += 2
        args = struct.unpack_from('<' + 'i' * arguments.get(name, 0), code, pos)
        pos += len(args) * 4
        if name == 'PUSH': stack.append(args[0])
        elif name == 'PUSHLOCALPAGE': stack.append(local)
        elif name == 'PUSHGLOBALPAGE': stack.append(global_)
        elif name == 'REF':
            index, page = stack.pop(), stack.pop()
            stack.append(page[index])
        elif name == 'A_REF':
            assert stack[-1] == 'character-id'
        elif name == 'DUP2': stack += stack[-2:]
        elif name == 'SWAP': stack[-2:] = stack[-2:][::-1]
        elif name == 'DELETE': release(stack.pop())
        elif name == 'ASSIGN':
            value, index, page = stack.pop(), stack.pop(), stack.pop()
            page[index] = value
            stack.append(value)
        elif name == 'SP_INC': refs[stack.pop()] += 1
        elif name == 'POP': stack.pop()
        elif name == 'NOT': stack.append(not stack.pop())
        elif name in ['GTE', 'EQUALE']:
            b, a = stack.pop(), stack.pop()
            stack.append(a >= b if name == 'GTE' else a == b)
        elif name == 'IFZ':
            if not stack.pop(): pos = args[0] - profile['Food']['Offset']
        elif name == 'CALLMETHOD':
            method_args = [stack.pop() for _ in range(args[0])][::-1]
            method, this = stack.pop(), stack.pop()
            calls.append(method)
            if method == profile['Food']['GetCharacter']:
                assert this == 200 and method_args == ['character-id']
                result = card_character
                refs[result] += 1
            elif method == profile['Food']['IsMax']:
                assert this == 300
                result = finished
            else: raise AssertionError('Unexpected method: %s' % method)
            stack.append(result)
        elif name == 'RETURN':
            result = bool(stack.pop())
            assert not stack, 'Operands leaked across return'
            for index in range(1, 3): release(local[index])
            assert all(value == 1 for value in refs.values()), 'Owned references leaked'
            return result, calls
        else: raise AssertionError('Unexpected opcode: ' + name)
    raise AssertionError('No return')


class FoodTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Windows native component')
    def test_native_write_rollback_and_execution_guards(self):
        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler.is_file(): self.skipTest('Windows .NET compiler not installed')
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='rance-food-test-') as folder:
            executable = Path(folder) / 'harness.exe'
            result = subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64',
                '/out:' + str(executable), '/r:System.Web.Extensions.dll', '/r:System.Core.dll', '/main:Harness',
                str(root / 'native/FoodSelector.cs'), str(root / 'tests/native_food_harness.cs')],
                capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace'))
            result = subprocess.run([str(executable)], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual(result.stdout.count(b'PASS '), 8)

    def test_target_filters_and_reference_cleanup(self):
        code = food.make_code(42, 300, bytes(PROFILE['Food']['Length']), PROFILE)
        self.assertEqual(len(code), PROFILE['Food']['Length'])
        for params, expected in [({}, True), ({'card_character': 43}, False), ({'finished': True}, False)]:
            with self.subTest(params=params):
                self.assertEqual(evaluate(code, **params)[0], expected)

    def test_caller_is_preserved_and_finished_fill_is_disabled(self):
        source = bytes(range(256)) + bytes(range(112))
        code = food.make_code(42, 300, source, PROFILE)
        first, second = PROFILE['Food']['FirstLength'], PROFILE['Food']['SecondOffset']
        self.assertEqual(code[first:second], source[first:second])
        self.assertFalse(evaluate(code[second:])[0])
        self.assertIn(PROFILE['Food']['IsMax'], evaluate(code)[1])

    def test_relocated_predicate_and_method_numbers_are_used(self):
        profile = dict(CharacterGlobal=57, Food=dict(Offset=0x8750, Length=420,
            FirstLength=128, SecondOffset=280, GetCharacter=1809, IsMax=1907))
        source = bytes(i % 256 for i in range(420))
        code = food.make_code(42, 300, source, profile)
        self.assertEqual(code[128:280], source[128:280])
        for params, expected in [({}, True), ({'card_character': 43}, False), ({'finished': True}, False)]:
            self.assertEqual(evaluate(code, profile=profile, **params)[0], expected)

    def test_invalid_live_handle_rejected(self):
        for handle in [-1, 0, 10000000, True, '42']:
            with self.assertRaises(ValueError): food.make_code(handle, 300, bytes(PROFILE['Food']['Length']), PROFILE)

    def test_helper_reply_is_matched_to_request(self):
        session = food.Session()
        class Input:
            def write(self, line):
                command = json.loads(line)
                session.answers.put(dict(request_id='timed-out-command', success=True, armed=True))
                session.answers.put(dict(request_id=command['request_id'], success=True, armed=False))
            def flush(self): pass
        class Process:
            stdin = Input()
        session.process = Process()
        with patch.object(session, 'start'):
            self.assertFalse(session.request(dict(action='cancel'))['armed'])

    def test_later_load_event_is_not_replaced_by_earlier_reply(self):
        session = food.Session()
        class Input:
            def write(self, line):
                command = json.loads(line)
                session.state = dict(armed=False, revision=2, reason='changed')
                session.answers.put(dict(request_id=command['request_id'], success=True, armed=True, revision=1))
            def flush(self):
                pass
        class Process:
            stdin = Input()
        session.process = Process()
        with patch.object(session, 'start'):
            session.request(dict(action='arm'))
        self.assertFalse(session.state['armed'])
        self.assertEqual(session.state['reason'], 'changed')

    def test_current_game_preflight_does_not_write_stale_save_target(self):
        session = food.Session()
        context = dict(training_cards=[dict(character='current', star=50,
                       story=dict(maximum=3, finished=False))])
        with patch.object(food.engine, 'check_live_version'), patch.object(food, 'live_context', return_value=context), \
             patch.object(session, 'request', return_value={'snapshot': {}}) as request:
            with self.assertRaisesRegex(ValueError, '当前游戏未持有'):
                session.arm('old-save-character')
            self.assertEqual(request.call_args.args[0]['action'], 'probe')
            self.assertEqual(request.call_count, 1)

    def test_no_story_and_completed_story_do_not_install_patch(self):
        for story in [dict(maximum=0, finished=True), dict(maximum=3, finished=True), None]:
            session = food.Session()
            context = dict(training_cards=[dict(character='target', star=80, story=story)])
            with patch.object(food.engine, 'check_live_version'), patch.object(food, 'live_context', return_value=context), \
                 patch.object(session, 'request', return_value={'snapshot': {}}) as request:
                with self.assertRaises(ValueError): session.arm('target')
                self.assertEqual(request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
