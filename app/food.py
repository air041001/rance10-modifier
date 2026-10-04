"""Temporary battle food-ticket selection; let the game build and play the scene."""
import base64
import json
import os
import queue
import struct
import subprocess
import threading
import time
import uuid
import app_paths
import character_data
import engine
import settings

OPS = dict(PUSH=0, POP=1, REF=2, PUSHGLOBALPAGE=4, PUSHLOCALPAGE=5,
           NOT=7, GTE=22, EQUALE=24, ASSIGN=25, DUP2=41, IFZ=45,
           RETURN=47, CALLMETHOD=92, SWAP=102, DELETE=119, A_REF=121, SP_INC=124)


class Code:
    def __init__(self):
        self.data, self.jumps = bytearray(), []

    def op(self, name, *args):
        self.data += struct.pack('<H', OPS[name])
        for arg in args:
            self.data += struct.pack('<i', arg)

    def local(self, index):
        self.op('PUSHLOCALPAGE'); self.op('PUSH', index); self.op('REF')

    def call(self, index, method):
        self.local(index); self.op('PUSH', method); self.op('CALLMETHOD', 0)

    def fail_if_false(self):
        self.op('IFZ', 0)
        self.jumps.append(len(self.data) - 4)

    def capture(self, index):
        # The caller owns the method's returned reference until frame cleanup.
        self.local(index); self.op('DELETE'); self.op('PUSHLOCALPAGE')
        self.op('SWAP'); self.op('PUSH', index); self.op('SWAP'); self.op('ASSIGN')

    def delete_local(self, index):
        self.op('PUSHLOCALPAGE'); self.op('PUSH', index); self.op('DUP2')
        self.op('REF'); self.op('DELETE'); self.op('PUSH', -1); self.op('ASSIGN'); self.op('POP')


def make_code(character_handle, story_handle, source, profile):
    layout = profile['Food']
    body_offset, body_length = layout['Offset'], layout['Length']
    first_length, second_offset = layout['FirstLength'], layout['SecondOffset']
    engine.require(all(type(handle) is int and 0 < handle < 10000000
                       for handle in [character_handle, story_handle]),
                   '运行中的人物标识无效，请重新读取。')
    engine.require(isinstance(source, bytes) and len(source) == body_length, '餐券筛选程序长度不一致。')
    c = Code()
    # Find's first Where lambda receives a string, with only two dummy slots.
    # Its caller still handles IsAvailable, unavailable cards, and deduplication.
    c.op('PUSHGLOBALPAGE'); c.op('PUSH', profile['CharacterGlobal']); c.op('REF')
    c.op('PUSH', layout['GetCharacter'])
    c.local(0); c.op('A_REF'); c.op('CALLMETHOD', 1)
    c.capture(1)  # Own the Character for the remainder of this frame.
    c.op('PUSH', character_handle); c.op('EQUALE'); c.fail_if_false()
    # Borrow its owned FoodTicketEvent; CALLMETHOD does not consume 'this'.
    c.op('PUSH', story_handle); c.op('PUSH', layout['IsMax']); c.op('CALLMETHOD', 0)
    c.op('NOT'); c.op('RETURN')  # Preserve the game's IsMax test.
    failure = body_offset + len(c.data)
    c.op('PUSH', 0); c.op('RETURN')
    for pos in c.jumps:
        struct.pack_into('<i', c.data, pos, failure)
    engine.require(len(c.data) <= first_length, '餐券筛选代码超出适配范围。')
    c.data.extend(b'\x01\x00' * ((first_length - len(c.data)) // 2))
    result = bytearray(source)
    result[:first_length] = c.data
    # Find normally fills empty slots with people whose stories are complete.
    # Disable only that fill lambda; leave its caller and map finder untouched.
    filler = Code(); filler.op('PUSH', 0); filler.op('RETURN')
    filler.data.extend(b'\x01\x00' * ((body_length - second_offset - len(filler.data)) // 2))
    result[second_offset:] = filler.data
    return bytes(result)


def live_context(snapshot):
    """Join current VM records to this installation's card/character metadata."""
    table, _ = engine.catalog()
    data = character_data.load()
    characters = {row['name']: row for row in snapshot['characters']}
    engine.require(len(characters) == len(snapshot['characters']), '运行中的人物记录重复，请稍后刷新。')
    rows = []
    for card in snapshot['cards']:
        row = table.get(card['id'])
        if not row or row['種別'] != 0 or row['识别名'] not in characters:
            continue
        name = row['识别名']
        char = characters[name]
        conditions = data['characters'].get(name)
        if char['story_key'] != data.get('character_root', '识别名情报') + '.' + name:
            conditions = None
        story = character_data.story(conditions, char['stage']) if conditions is not None else None
        rows.append(dict(id=card['id'], character=name, faction=engine.ORG_NAMES[card['faction']],
                         star=char['star'], exp=char['exp'], next_exp=char['next_exp'],
                         enhancement=card['count'] - 1, overridden=card['overridden'], story=story))
    return dict(source='live', manual=False, pending=[], training_cards=rows,
                star_cap=data['star_cap'], enhancement_cap=data['enhancement_cap'],
                pid=snapshot['pid'], session=snapshot['session'])


class Session:
    def __init__(self, changed=lambda state: None):
        self.changed, self.process = changed, None
        self.answers, self.events = queue.Queue(), queue.Queue()
        self.lock = threading.Lock()
        self.game_dir = None
        self.state = dict(armed=False, message='尚未指定战后餐券人物。')

    def start(self):
        game_dir = str(settings.game_dir().resolve())
        profile_path = str(engine.check_live_version())
        if self.process and self.process.poll() is None:
            if self.game_dir == game_dir and getattr(self, 'profile_path', None) == profile_path and not self.process.stdin.closed:
                return
            self._stop()
            engine.require(self.process.poll() is not None, '正在取消原游戏目录的指定，请稍后重试。')
        self.answers = queue.Queue()
        self.state = dict(armed=False, message='尚未指定战后餐券人物。')
        self.game_dir = game_dir
        self.profile_path = profile_path
        self.process = subprocess.Popen([str(app_paths.RESOURCE_DIR / 'LiveValues.exe'),
            '--food-watch', '--parent-pid', str(os.getpid()), '--game-dir', game_dir, '--runtime-profile', profile_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self.read, args=(self.process, self.answers), daemon=True).start()

    def read(self, process, answers):
        for line in process.stdout:
            try:
                state = json.loads(line)
            except ValueError:
                continue
            if process is self.process:
                self.state = state
            if state.get('reply'):
                answers.put(state)
            elif process is self.process:
                self.events.put((process, state))
        answers.put(dict(success=False, exited=True, armed=False, message='餐券运行组件已退出，请重试。'))
        if process is self.process:
            self.state = dict(success=False, armed=False, message='餐券指定已结束。')
            self.events.put((process, self.state))

    def request(self, command):
        with self.lock:
            self.start()
            ident = uuid.uuid4().hex
            command = dict(command, request_id=ident)
            self.process.stdin.write(json.dumps(command, ensure_ascii=False) + '\n')
            self.process.stdin.flush()
            deadline = time.monotonic() + 20
            try:
                while True:
                    state = self.answers.get(timeout=max(0, deadline - time.monotonic()))
                    if state.get('request_id') == ident or state.get('exited'):
                        break
            except queue.Empty:
                self.process.stdin.close()  # The helper restores in its finally block.
                raise ValueError('餐券运行组件响应超时，正在取消指定，请稍后重试。')
            if state.get('revision', 0) >= self.state.get('revision', 0):
                self.state = state
            if not state.get('success'):
                self.events.put((self.process, state))
                raise ValueError(state.get('message', '餐券指定未完成。'))
            return state

    def inspect(self):
        engine.check_live_version()
        return live_context(self.request(dict(action='probe'))['snapshot'])

    def arm(self, character):
        engine.check_live_version()
        snapshot = self.request(dict(action='probe'))['snapshot']
        context = live_context(snapshot)
        rows = [row for row in context['training_cards'] if row['character'] == character]
        engine.require(rows, '当前游戏未持有“%s”的人物卡，请读取当前游戏人物。' % character)
        story = rows[0]['story']
        engine.require(story is not None, '本机游戏数据中未找到此人物的餐券故事，请选择有故事的人物。')
        engine.require(story['maximum'] > 0, '“%s”没有可播放的餐券故事。' % character)
        engine.require(not story['finished'], '“%s”的餐券故事已完成。' % character)
        target = next(row for row in snapshot['characters'] if row['name'] == character)
        patch = make_code(target['handle'], target['story_handle'], base64.b64decode(snapshot['source_code']), snapshot['profile'])
        state = self.request(dict(action='arm', character=character, character_handle=target['handle'],
            character_page=target['page'], stage=target['stage'], maximum=story['maximum'],
            story_handle=target['story_handle'], story_page=target['story_page'],
            story_key=target['story_key'],
            pid=snapshot['pid'], session=snapshot['session'], card_ids=[row['id'] for row in rows],
            patch=base64.b64encode(patch).decode('ascii')))
        latest = dict(self.state)
        if latest.get('character') == character:
            latest['card_id'] = rows[0]['id']
        return latest

    def cancel(self):
        return self.request(dict(action='cancel'))

    def poll(self):
        while not self.events.empty():
            process, state = self.events.get_nowait()
            if process is self.process:
                self.changed(state)

    def _stop(self):
        if self.process and self.process.poll() is None:
            try:
                if not self.process.stdin.closed:
                    self.process.stdin.close()
                self.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                # The helper watches its parent and restores independently.
                pass

    def close(self):
        with self.lock:
            self._stop()
