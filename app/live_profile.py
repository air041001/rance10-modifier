"""Read the selected game's AIN metadata for sys43vm runtime operations.

The file layout is read directly; no game resources or code are installed with
the modifier. Only field maps and digests are cached on the user's machine.
"""
import hashlib
import json
import struct
import zlib
from pathlib import Path
import app_paths
import save_compat


class Reader:
    def __init__(self, data):
        self.data, self.pos, self.version = data, 0, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError('游戏脚本数据不完整。')
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def integer(self):
        return struct.unpack('<i', self.take(4))[0]

    def count(self, maximum=100000):
        value = self.integer()
        if not 0 <= value <= maximum:
            raise ValueError('游戏脚本记录数量无效。')
        return value

    def text(self):
        end = self.data.find(b'\0', self.pos, self.pos + 65536)
        if end < 0:
            raise ValueError('游戏脚本名称缺少终止符。')
        # Required structural names are ASCII. Preserve other names losslessly
        # without guessing the encoding of a translated script.
        return self.take(end - self.pos + 1)[:-1].decode('latin-1')

    def typ(self, depth=0):
        if depth > 8:
            raise ValueError('游戏脚本类型嵌套过深。')
        data, structure, rank = self.integer(), self.integer(), self.integer()
        if rank not in (0, 1):
            raise ValueError('游戏脚本子类型标记无效。')
        child = self.typ(depth + 1) if rank else None
        return (data, structure, rank, child)

    def variable(self):
        name = self.text()
        if self.version >= 12:
            self.text()
        typ = self.typ()
        if self.version >= 8 and self.integer():
            if typ[0] == 12:
                self.text()
            elif typ[0] not in (13, 63, 79, 80, 18, 19, 20, 21, 22, 23, 24, 25, 31, 32, 51, 52, 59, 60, 67, 69):
                self.integer()
        return dict(name=name, type=typ)


def parse_ain(raw):
    if raw[:8] == b'AI2\0\0\0\0\0':
        if len(raw) < 16:
            raise ValueError('游戏脚本文件头不完整。')
        plain_size, compressed_size = struct.unpack_from('<II', raw, 8)
        if not 0 < plain_size <= 128 * 1024 * 1024 or compressed_size != len(raw) - 16:
            raise ValueError('游戏脚本压缩长度无效。')
        inflater = zlib.decompressobj()
        try:
            plain = inflater.decompress(raw[16:], plain_size + 1)
        except zlib.error as exc:
            raise ValueError('游戏脚本压缩数据无效。') from exc
        if len(plain) != plain_size or not inflater.eof or inflater.unused_data:
            raise ValueError('游戏脚本解压结果不完整。')
    elif raw[:4] == b'VERS':
        plain = raw
    else:
        raise ValueError('实时功能尚未支持这个脚本容器。卡牌功能可独立使用。')
    r = Reader(plain)
    if r.take(4) != b'VERS':
        raise ValueError('游戏脚本缺少版本标记。')
    r.version = r.integer()
    if r.version not in (11, 12):
        raise ValueError('实时功能尚未支持AIN %d格式。' % r.version)
    result = dict(version=r.version, functions=[], globals=[], structures=[])
    while r.pos < len(plain):
        tag = r.take(4)
        if tag == b'KEYC':
            r.integer()
        elif tag == b'CODE':
            result['code'] = r.take(r.count(64 * 1024 * 1024))
        elif tag == b'FUNC':
            for index in range(r.count()):
                address, name = r.integer(), r.text()
                returned = r.typ()
                argc, varc = r.count(1024), r.count(4096)
                r.integer()  # lambda flag
                r.integer()  # CRC
                variables = [r.variable() for _ in range(varc)]
                if argc > varc:
                    raise ValueError('游戏函数参数数量无效。')
                result['functions'].append(dict(index=index, address=address, name=name,
                                               returned=returned, argc=argc, variables=variables))
        elif tag == b'GLOB':
            for index in range(r.count(10000)):
                name = r.text()
                if r.version >= 12:
                    r.text()
                typ = r.typ()
                r.integer()  # group
                result['globals'].append(dict(index=index, name=name, type=typ))
        elif tag == b'GSET':
            for _ in range(r.count()):
                r.integer()
                if r.integer() == 12:
                    r.text()
                else:
                    r.integer()
        elif tag == b'STRT':
            for index in range(r.count(10000)):
                name = r.text()
                r.take(r.count(1024) * 8)  # interfaces
                r.integer(); r.integer()  # constructor/destructor
                members = [r.variable() for _ in range(r.count(4096))]
                result['structures'].append(dict(index=index, name=name, members=members))
            break  # Later sections are not needed by runtime operations.
        else:
            raise ValueError('游戏脚本结构段顺序尚未支持：' + repr(tag))
    if not all(result.get(name) for name in ['code', 'functions', 'globals', 'structures']):
        raise ValueError('游戏脚本缺少实时功能所需的结构。')
    return result


SCHEMAS = dict(save_compat.SCHEMAS,
    PartyBonusSwitcher=[(63, 'm_onChange'), (79, 'm_bonus'), (10, 'm_maxPoint')])
# Runtime reads use these slots; unused save fields do not gate a live feature.
USED = dict(PlayerCardCollection={'m_org'}, OrganizationCardCollection={'m_card'},
            PlayerCard={'m_dummyStar', 'm_tempStar', 'm_count', '<Id>'},
            Character={'m_id', 'm_star', '<Exp>', '<NextExp>', '<FoodTicketEvent>'})
for _name, _used in USED.items():
    SCHEMAS[_name] = [(typ, name if name in _used else '') for typ, name in SCHEMAS[_name]]
REQUIRED = ['PlayerCommonParam', 'PartyBonusSwitcher', 'Character', 'CharacterCollection',
            'FoodTicketEvent', 'PlayerCard', 'PlayerCardCollection', 'OrganizationCardCollection']
GLOBALS = dict(PlayerGlobal='g_playerCommonParam', BonusGlobal='g_partyBonus',
               CharacterGlobal='g_character', CardGlobal='g_playerCard')


def describe(ain, include_food=True):
    structures = {row['name']: row for row in ain['structures']}
    fields, counts = {}, {}
    for name in (REQUIRED if include_food else REQUIRED[:2]):
        if name not in structures:
            raise ValueError('游戏脚本缺少实时结构：' + name)
        members = structures[name]['members']
        positions = {row['name']: (index, row['type']) for index, row in enumerate(members) if row['name']}
        wanted = SCHEMAS[name]
        if len(positions) != sum(bool(row['name']) for row in members):
            raise ValueError('游戏脚本字段重复：' + name)
        mapping = []
        for typ, field in wanted:
            if not field:
                mapping.append(-1)  # Unused slot in the normalized record.
                continue
            actual = positions.get(field)
            compatible = (79, 80) if typ == 79 else (typ,)
            if actual is None or actual[1][0] not in compatible:
                raise ValueError('实时字段类型需要适配：' + name + '.' + field)
            mapping.append(actual[0])
        fields[name], counts[name] = mapping, len(members)
    if include_food:
        for name, field, target in [('Character', '<FoodTicketEvent>', 'FoodTicketEvent'),
                ('CharacterCollection', 'm_character', 'Character'),
                ('PlayerCardCollection', 'm_org', 'OrganizationCardCollection'),
                ('OrganizationCardCollection', 'm_card', 'PlayerCard')]:
            typ = next(m['type'] for m in structures[name]['members'] if m['name'] == field)
            leaf = typ[3] if typ[0] in (79, 80) else typ
            if not leaf or leaf[0] != 13 or leaf[1] != structures[target]['index']:
                raise ValueError('实时对象引用需要适配：' + name + '.' + field)
    result = dict(Schema=1, GlobalCount=len(ain['globals']), Fields=fields, Counts=counts,
                  CodeLength=len(ain['code']), CharacterGlobal=0, CardGlobal=0)
    for key, name in GLOBALS.items():
        if not include_food and key in ('CharacterGlobal', 'CardGlobal'):
            continue
        matches = [row for row in ain['globals'] if row['name'] == name]
        expected_type = {'PlayerGlobal': 'PlayerCommonParam', 'BonusGlobal': 'PartyBonusSwitcher',
                         'CharacterGlobal': 'CharacterCollection', 'CardGlobal': 'PlayerCardCollection'}[key]
        if len(matches) != 1 or matches[0]['type'][0] != 13 or matches[0]['type'][1] != structures[expected_type]['index']:
            raise ValueError('实时全局对象需要适配：' + name)
        result[key] = matches[0]['index']
    # Optional display metadata. Unknown chapter layouts never gate resource edits.
    result['GameGlobal'] = -1
    context = structures.get('GameContext')
    matches = [g for g in ain['globals'] if g['name'] == 'g_gameContext']
    if context and len(matches) == 1 and matches[0]['type'][:2] == (13, context['index']):
        chapter = [(i, m) for i, m in enumerate(context['members']) if m['name'] == 'm_chapter']
        if len(chapter) == 1 and chapter[0][1]['type'][0] == 92:
            result['GameGlobal'] = matches[0]['index']
            fields['GameContext'] = [chapter[0][0]]
            counts['GameContext'] = len(context['members'])
    return result


def predicate(ain, function, references=None):
    """Fingerprint a small predicate by operations and resolved symbol names."""
    code, start = ain['code'], function['address']
    if not 0 <= start < len(code):
        raise ValueError('餐券筛选函数地址无效。')
    pos, operations = start, []
    symbols = {f['index']: f['name'] for f in ain['functions']}
    globals_ = {g['index']: g['name'] for g in ain['globals']}
    allowed = {0, 1, 2, 4, 5, 7, 25, 41, 47, 92, 102, 119, 121, 124, 126}
    while pos < min(len(code), start + 2048):
        opcode = struct.unpack_from('<H', code, pos)[0]
        pos += 2
        if opcode not in allowed:
            raise ValueError('餐券筛选规则有变化，需要单独适配。')
        args = []
        if opcode in (0, 92, 126):
            value = struct.unpack_from('<i', code, pos)[0]
            pos += 4
            if opcode == 126:
                if value != function['index']:
                    raise ValueError('餐券筛选函数结束标记无效。')
                operations.append([opcode])
                return pos - start, hashlib.sha256(json.dumps(operations).encode()).hexdigest()
            if opcode == 0 and operations and operations[-1][0] == 4:
                value = globals_.get(value, 'unknown-global')
            elif opcode == 0 and value in symbols and value > 1000:
                if references is not None:
                    references.setdefault(symbols[value], set()).add(value)
                value = symbols[value]
            args.append(value)
        operations.append([opcode] + args)
    raise ValueError('餐券筛选函数不完整。')


# Digests of the instruction shapes, not game-file or translation fingerprints.
PREDICATES = ('d164718af99000bb3269eeca829c88ddfaab2689c405438a0b1942b18ef140aa',
              '94c04fba628cec0e52ba44035db4ed602930c88edea4b2b1dac2c2ee18423e84')


def food_profile(ain):
    lambdas = sorted((f for f in ain['functions'] if f['name'].startswith('<lambda : FoodTicketTargetFinder::Find()(')),
                     key=lambda f: f['address'])
    if len(lambdas) != 2:
        raise ValueError('未找到战后餐券的两个筛选入口。')
    references = {}
    shapes = [predicate(ain, f, references) for f in lambdas]
    if tuple(digest for _, digest in shapes) != PREDICATES:
        raise ValueError('战后餐券筛选规则有变化，需要单独适配；餐券和部队点数可独立使用。')
    if any(f['argc'] != 1 or len(f['variables']) != 3 or f['returned'][0] != 47
           or f['variables'][0]['type'][0] != 12 for f in lambdas):
        raise ValueError('餐券筛选参数需要适配。')
    start, second = lambdas[0]['address'], lambdas[1]['address']
    length = second + shapes[1][0] - 6 - start
    if not 80 <= shapes[0][0] <= second - start or not 8 <= shapes[1][0] <= 2048 or length > 8192:
        raise ValueError('餐券筛选代码范围无效。')
    by_name = {}
    for f in ain['functions']:
        by_name.setdefault(f['name'], []).append(f)
    methods = {}
    for name in ['CharacterCollection@Get', 'FoodTicketEvent@IsMax::get']:
        indices = references.get(name, set())
        if len(indices) != 1:
            raise ValueError('餐券调用方法需要适配：' + name)
        methods[name] = next(f for f in ain['functions'] if f['index'] in indices)
    structures = {s['name']: s['index'] for s in ain['structures']}
    get, is_max = methods['CharacterCollection@Get'], methods['FoodTicketEvent@IsMax::get']
    if (get['argc'] != 1 or get['variables'][0]['type'][0] != 12 or
        get['returned'][:2] != (21, structures['Character']) or
        is_max['argc'] != 0 or is_max['returned'][0] != 47):
        raise ValueError('餐券调用参数需要适配。')
    for f in lambdas:
        if [v['type'][:2] for v in f['variables'][1:]] != [(21, structures['Character']), (21, structures['FoodTicketEvent'])]:
            raise ValueError('餐券局部对象类型需要适配。')
    if any(len(by_name.get(n, [])) != 1 for n in ['FoodTicketTargetFinder::Find', 'FoodTicketTargetFinder::FindAfter']):
        raise ValueError('餐券入口需要适配。')
    span = ain['code'][start:start + length]
    return dict(Offset=start, Length=length, FirstLength=shapes[0][0]-6, SecondOffset=second-start,
                SpanHash=hashlib.sha256(span).hexdigest(),
                GuardStart=by_name['FoodTicketTargetFinder::Find'][0]['address'],
                GuardEnd=by_name['FoodTicketTargetFinder::FindAfter'][0]['address'],
                GetCharacter=get['index'], IsMax=is_max['index'])


def battle_profile(ain):
    """Resolve the four country counters from the game's flag accessors.

    The flag base and VM global are installation data, not executable offsets.
    Check both read/write paths before treating any flag as a battle result.
    """
    names = {0: 'P', 1: 'POP', 2: 'REF', 4: 'G', 5: 'L', 9: 'ADD', 10: 'SUB',
             21: 'LE', 24: 'EQ', 25: 'SET', 41: 'DUP2', 42: 'DUP_X2',
             44: 'JUMP', 45: 'IFZ', 46: 'IFNZ', 47: 'RET', 48: 'CALL',
             90: 'HLL', 91: 'S', 98: 'EOF', 102: 'SWAP', 109: 'R_SET',
             119: 'DEL', 123: 'DUP_U2'}
    functions = sorted(ain['functions'], key=lambda f: f['address'])
    symbols = {f['index']: f['name'] for f in functions}
    globals_ = {g['index']: g['name'] for g in ain['globals']}

    def shape(name):
        matches = [(i, f) for i, f in enumerate(functions) if f['name'] == name]
        if len(matches) != 1:
            raise ValueError('未找到战果访问入口：' + name)
        index, function = matches[0]
        start = function['address']
        end = functions[index + 1]['address'] - 6 if index + 1 < len(functions) else len(ain['code'])
        if not 0 <= start < end <= len(ain['code']) or end - start > 2048:
            raise ValueError('战果访问代码范围无效。')
        pos, operations, locations = start, [], {}
        while pos < end:
            locations[pos] = len(operations)
            opcode = struct.unpack_from('<H', ain['code'], pos)[0]
            if opcode not in names:
                raise ValueError('战果访问规则需要适配。')
            count = 3 if opcode == 90 else int(opcode in (0, 44, 45, 46, 48, 98))
            pos += 2
            args = list(struct.unpack_from('<' + 'i' * count, ain['code'], pos))
            pos += count * 4
            if pos > end:
                raise ValueError('战果访问代码不完整。')
            operations.append([opcode] + args)
        tokens = []
        for index, row in enumerate(operations):
            opcode, args = row[0], row[1:]
            if opcode == 98:
                if index != len(operations) - 1:
                    raise ValueError('战果函数结束位置无效。')
                continue
            if opcode == 0 and index and operations[index - 1][0] == 4:
                args = [globals_.get(args[0], '?')]
            elif opcode == 48:
                args = [symbols.get(args[0], '?')]
            elif opcode in (44, 45, 46):
                if args[0] not in locations:
                    raise ValueError('战果访问分支无效。')
                args = [locations[args[0]]]
            elif opcode == 90:
                # Library/function ordinals can move. This code is not called
                # by the modifier; the typed int array is accessed directly.
                args = ['array', args[2]]
            tokens.append(names[opcode] + (':' + ','.join(map(str, args)) if args else ''))
        return tokens

    get = shape('TadaFlagFunc::GetAchieve')
    if len(get) != 37 or not get[2].startswith('P:') or not get[20].startswith('P:'):
        raise ValueError('战果国家索引需要适配。')
    first, last = int(get[2][2:]), int(get[20][2:])
    expected_get = ('L P:1 P:{first} L P:0 REF P:1 SUB ADD SET POP P:{first} L P:1 REF LE '
                    'IFZ:25 L P:1 REF P:{last} LE IFZ:25 P:1 JUMP:26 P:0 IFNZ:28 JUMP:33 '
                    'L P:1 REF CALL:TadaFlagFunc::Get RET P:0 RET P:0 RET').format(first=first, last=last)
    expected_set = ('L P:2 P:{first} L P:0 REF P:1 SUB ADD SET POP P:{first} L P:2 REF LE '
                    'IFZ:25 L P:2 REF P:{last} LE IFZ:25 P:1 JUMP:26 P:0 IFNZ:28 JUMP:35 '
                    'L P:2 REF L P:1 REF CALL:TadaFlagFunc::Set RET').format(first=first, last=last)
    checks = {
        'TadaFlagFunc::GetAchieve': expected_get,
        'TadaFlagFunc::SetAchieve': expected_set,
        'TadaFlagFunc::Get': 'G P:tt REF L P:0 REF HLL:array,10 L P:1 REF DEL L DUP_X2 POP P:1 DUP_X2 POP R_SET DUP_U2 P:-1 EQ IFZ:33 POP POP P:-1 L SWAP P:3 SWAP SET POP L P:3 REF RET P:0 RET',
        'TadaFlagFunc::Set': 'G P:tt REF L P:0 REF HLL:array,10 L P:2 REF DEL L DUP_X2 POP P:2 DUP_X2 POP R_SET L P:1 REF SET POP L P:2 DUP2 REF DEL P:-1 SET POP RET',
    }
    for name, expected in checks.items():
        if shape(name) != expected.split():
            raise ValueError('战果访问规则需要适配：' + name)
    flags = [g for g in ain['globals'] if g['name'] == 'tt']
    if (len(flags) != 1 or flags[0]['type'][0] not in (79, 80) or
            flags[0]['type'][3] != (10, -1, 0, None) or not 0 <= first <= last < 10000 or last - first != 3):
        raise ValueError('战果旗标数组需要适配。')
    country = next((s for s in ain['structures'] if s['name'] == 'Country'), None)
    if not country:
        raise ValueError('缺少战果国家结构。')
    ids = [(i, m) for i, m in enumerate(country['members']) if m['name'] == 'm_id']
    if len(ids) != 1 or ids[0][1]['type'][0] != 10:
        raise ValueError('战果国家字段需要适配。')
    field = ids[0][0]
    if (shape('Country@GetAchieve') != ('S P:%d REF CALL:TadaFlagFunc::GetAchieve RET P:0 RET' % field).split() or
            shape('Country@SetAchieve') != ('S P:%d REF P:3 L P:0 REF HLL:array,-1 CALL:TadaFlagFunc::SetAchieve RET' % field).split()):
        raise ValueError('战果国家访问规则或上限需要适配。')
    return dict(FlagGlobal=flags[0]['index'], FirstIndex=first, LastIndex=last, Maximum=3)


def prepare(game):
    game = Path(game)
    raw = (game / 'Rance10.ain').read_bytes()
    ain_hash = hashlib.sha256(raw).hexdigest()
    exe_hash = save_compat.file_hash(game / 'Rance10.exe')
    codepage = 932
    try:
        catalog = json.loads(app_paths.CATALOG_FILE.read_text(encoding='utf-8'))
        if catalog.get('source', {}).get('ex_sha256') == save_compat.file_hash(game / 'Rance10EX.ex'):
            codepage = {'CP936': 936, 'CP932': 932}[catalog['source']['encoding']]
    except (OSError, ValueError, KeyError):
        pass
    identity = hashlib.sha256(('%s:%s:%d:5' % (ain_hash, exe_hash, codepage)).encode()).hexdigest()
    folder = app_paths.CACHE_DIR / 'live-profiles'
    target = folder / (identity + '.json')
    if target.is_file():
        try:
            data = json.loads(target.read_text(encoding='utf-8'))
            checked = hashlib.sha256(json.dumps({k: v for k, v in data.items() if k != 'ContentDigest'},
                                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if data.get('ContentDigest') == checked and data.get('AinHash') == ain_hash and data.get('ExeHash') == exe_hash:
                return target, data
        except (OSError, ValueError, AttributeError):
            pass  # Rebuild a missing or damaged derived cache from the game.
    ain = parse_ain(raw)
    data = describe(ain, include_food=False)
    try:
        complete = describe(ain)
        data['Food'] = food_profile(ain)
        data.update(complete)
    except (ValueError, KeyError, struct.error) as exc:
        data['Food'] = None
        data['FoodError'] = str(exc)
    try:
        data['Battle'] = battle_profile(ain)
    except (ValueError, KeyError, struct.error) as exc:
        data['Battle'] = None
        data['BattleError'] = str(exc)
    proof = bytearray(ain['code'])
    if data['Food']:
        food = data['Food']
        proof[food['Offset']:food['Offset'] + food['Length']] = b'\0' * food['Length']
    data.update(AinHash=ain_hash, ExeHash=exe_hash, CodePage=codepage,
                CodeHash=hashlib.sha256(proof).hexdigest())
    data['ContentDigest'] = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if ain_hash != save_compat.file_hash(game / 'Rance10.ain') or exe_hash != save_compat.file_hash(game / 'Rance10.exe'):
        raise ValueError('游戏文件刚刚发生变化，请重试。')
    folder.mkdir(parents=True, exist_ok=True)
    import uuid
    temporary = target.with_name(identity + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target, data
