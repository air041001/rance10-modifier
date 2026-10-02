"""Local Rance 10 v8 save editor. No network and no runtime memory writes."""
from pathlib import Path
import bisect
import copy
import datetime
import hashlib
import json
import os
import re
import shutil
import struct
import uuid
import zlib
import app_paths
import settings
from game_profile import GAME_HASHES
import save_compat

BASE = app_paths.RESOURCE_DIR
SAVE_DIR = settings.save_dir()
BACKUP_DIR = settings.backup_dir()
ORG_NAMES = ['', '主人公', '利萨斯', '赫尔曼', '赛斯', '自由都市', 'JAPAN', '其他', '亚人', '怪物', '神魔']
CARD_KINDS = {0: '人物', 5: '通用', 10: '物品'}
EX_HASH = 'd340aaf2b0856e784943181734d5b7f47637a0cb750aebd1fb3db581ba678837'
EXE_HASH = '39a508c05b13afc5427f0b722fce5c4edeced126587e037d585cf0e70d279297'


def configure():
    global SAVE_DIR, BACKUP_DIR
    SAVE_DIR = settings.save_dir()
    BACKUP_DIR = settings.backup_dir()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pack(*vals):
    return struct.pack('<' + 'i' * len(vals), *vals)


class Reader:
    def __init__(self, data, pos=0, encoding='gbk'):
        self.b, self.p, self.encoding = data, pos, encoding

    def i(self):
        result = struct.unpack_from('<i', self.b, self.p)[0]
        self.p += 4
        return result

    def text(self):
        end = self.b.index(0, self.p)
        result = self.b[self.p:end].decode(self.encoding, errors='strict')
        self.p = end + 1
        return result


def parse(raw, filename='', encoding=None):
    encoding = encoding or save_compat.encoding()
    require(raw[:4] == b'GD\x01\x01', '不是受支持的兰斯10存档。')
    size = struct.unpack_from('<i', raw, 4)[0]
    require(0 < size < 32 * 1024 * 1024, '存档长度异常。')
    dec = zlib.decompressobj()
    data = dec.decompress(raw[8:], size + 1)
    require(dec.eof and len(data) == size and not dec.unused_data, '存档压缩数据不完整。')
    r = Reader(data, encoding=encoding)
    key = r.text()
    h = [r.i() for _ in range(14)]
    require(key == 'rance10' and h[1] == 8 and h[2] == 64, '当前仅支持兰斯10的v8格式存档。')
    require(64 < h[4] <= h[6] <= h[8] <= h[10] <= h[12] <= size, '存档目录无效。')
    require(all(0 <= h[i] < 1000000 for i in [5, 7, 9, 11, 13]), '存档计数无效。')
    r.p = h[4]
    records = []
    for _ in range(h[5]):
        sid, n = r.i(), r.i()
        require(0 <= n < 10000, '记录长度异常。')
        records.append({'sid': sid, 'kv': [r.i() for _ in range(n)]})
    require(r.p == h[6], '记录区长度错误。')
    globals_ = {}
    for _ in range(h[7]):
        typ, value, name = r.i(), r.i(), r.text()
        require(not name or name not in globals_, '存档全局字段名重复：' + name)
        globals_[name] = (typ, value)
    require(r.p == h[8], '全局数据区长度错误。')
    strings = [r.text() for _ in range(h[9])]
    require(r.p == h[10], '字符串区长度错误。')
    arrays = []
    for _ in range(h[11]):
        rank = r.i()
        require(-1 <= rank <= 8, '数组维数异常。')
        dims = [r.i() for _ in range(max(rank, 0))]
        flats = r.i()
        require(0 <= flats < 100000, '数组长度异常。')
        parts = []
        for _ in range(flats):
            n, typ = r.i(), r.i()
            require(0 <= n < 1000000, '数组元素数量异常。')
            parts.append({'type': typ, 'values': [r.i() for _ in range(n)]})
        arrays.append({'rank': rank, 'dims': dims, 'flat': parts})
    require(r.p == h[12], '数组区长度错误。')
    kv = [r.i() for _ in range(h[13])]
    defs = []
    for _ in range(r.i()):
        name, n = r.text(), r.i()
        members = [(r.i(), r.text()) for _ in range(n)]
        defs.append({'name': name, 'fields': members})
    result = dict(file=filename, raw=raw, payload=data, header=h, records=records,
                  globals=globals_, strings=strings, arrays=arrays, kv=kv, defs=defs,
                  defs_end=r.p, extra_strings=[], encoding=encoding)
    metadata(result)
    return result


def metadata(s):
    b = s['payload']
    pos = struct.unpack_from('<I', b, s['header'][2])[0]
    require(pos == s['defs_end'], '存档说明位置无效；没有写入。')
    length = struct.unpack_from('<I', b, pos)[0]
    require(pos + 4 + length == len(b), '存档说明长度无效。')
    raw = b[pos + 4:]
    pieces = raw.decode(s['encoding'], errors='strict').split('|', 6)
    require(len(pieces) == 7 and pieces[0].isdigit(), '存档位说明无效。')
    name = Path(s['file']).name
    match = re.fullmatch(r'LocalSave(\d+)\.asd', name)
    if match:
        require(int(pieces[0]) == int(match[1]), '文件名与存档位说明不一致。')
    return dict(slot=int(pieces[0]), time=pieces[5], comment=pieces[6].strip(), raw=raw)


def fields(s, ref):
    require(0 <= ref < len(s['records']), '卡牌记录引用无效。')
    rec = s['records'][ref]
    require(0 <= rec['sid'] < len(s['defs']), '卡牌结构引用无效。')
    names = s['defs'][rec['sid']]['fields']
    require(len(names) == len(rec['kv']), '卡牌字段数量不一致。')
    require(len({name for _, name in names if name}) == sum(bool(name) for _, name in names), '记录字段名重复。')
    require(all(0 <= idx < len(s['kv']) for idx in rec['kv']), '记录字段索引越界。')
    return {name: s['kv'][idx] for (_, name), idx in zip(names, rec['kv'])}


def field_index(s, ref, name):
    fields(s, ref)
    rec = s['records'][ref]
    pos = [i for i, (_, n) in enumerate(s['defs'][rec['sid']]['fields']) if n == name]
    require(len(pos) == 1, '字段不唯一：' + name)
    return rec['kv'][pos[0]]


def flat(s, ref, typ):
    require(0 <= ref < len(s['arrays']), '数组引用无效。')
    a = s['arrays'][ref]
    require(a['rank'] == 1 and len(a['flat']) == 1 and a['flat'][0]['type'] == typ,
            '卡牌数组结构不匹配。')
    require(a['dims'] == [len(a['flat'][0]['values'])], '卡牌数组维数不匹配。')
    return a['flat'][0]['values']


def text(s, index):
    require(0 <= index < len(s['strings']), '字符串引用无效。')
    return s['strings'][index]


def resize(s, index):
    s['arrays'][index]['dims'] = [len(s['arrays'][index]['flat'][0]['values'])]


def addstr(s, value):
    if value in s['strings']:
        return s['strings'].index(value)
    s['strings'].append(value)
    s['extra_strings'].append(value.encode(s['encoding']) + b'\0')
    return len(s['strings']) - 1


def addrecord(s, name, values):
    ids = [i for i, d in enumerate(s['defs']) if d['name'] == name]
    require(len(ids) == 1, '未找到唯一的结构：' + name)
    save_compat.validate_save(s, exact=[name])
    require([n for _, n in s['defs'][ids[0]]['fields']] == list(values), '结构字段不匹配：' + name)
    indices = []
    for value in values.values():
        indices.append(len(s['kv']))
        s['kv'].append(value)
    ref = len(s['records'])
    s['records'].append({'sid': ids[0], 'kv': indices})
    return ref


def array_bytes(a):
    result = pack(a['rank'], *a['dims'], len(a['flat']))
    for part in a['flat']:
        result += pack(len(part['values']), part['type'], *part['values'])
    return result


def build_payload(s, original):
    b, h = original['payload'], original['header']
    out, newh = bytearray(b[:h[4]]), h.copy()
    out += b[h[4]:h[6]]
    for r in s['records'][len(original['records']):]:
        out += pack(r['sid'], len(r['kv']), *r['kv'])
    newh[5], newh[6] = len(s['records']), len(out)
    out += b[h[6]:h[8]]
    newh[8] = len(out)
    out += b[h[8]:h[10]] + b''.join(s['extra_strings'])
    newh[9], newh[10] = len(s['strings']), len(out)
    for a in s['arrays']:
        out += array_bytes(a)
    newh[11], newh[12] = len(s['arrays']), len(out)
    out += pack(*s['kv'])
    newh[13] = len(s['kv'])
    out += b[h[12] + h[13] * 4:]
    struct.pack_into('<14i', out, 8, *newh)
    oldfooter = struct.unpack_from('<I', b, h[2])[0]
    struct.pack_into('<I', out, h[2], oldfooter + len(out) - len(b))
    return bytes(out)


def catalog_data():
    from assets import validate_catalog
    require(app_paths.CATALOG_FILE.is_file(), '请先在“设置”中准备卡牌图鉴。')
    data = json.loads(app_paths.CATALOG_FILE.read_text(encoding='utf-8'))
    validate_catalog(data)
    return data


def catalog():
    data = catalog_data()
    return {r['Id']: r for r in data['cards']}, {r['Id']: r for r in data['skills']}


def check_version():
    validate_game(settings.game_dir())


def validate_game(game):
    game = Path(game)
    for name, expected in GAME_HASHES.items():
        path = game / name
        require(path.is_file(), '所选目录缺少 ' + name + '，请选择游戏程序所在文件夹。')
        require(sha(path.read_bytes()) == expected, '游戏版本尚未适配（' + name + '），已停止修改。')
    return game


def validate_game_directory(game):
    game = Path(game)
    for name in GAME_HASHES:
        require((game / name).is_file(), '所选目录缺少 ' + name + '，请选择游戏程序所在文件夹。')
    return game


def check_live_version():
    game = validate_game_directory(settings.game_dir())
    for name in ['Rance10.exe', 'Rance10.ain']:
        require(save_compat.file_hash(game / name) == GAME_HASHES[name],
                '实时修改尚未适配此游戏版本（' + name + '）。卡牌功能按本机数据单独检查。')


def collection(s):
    save_compat.validate_save(s)
    rootref = s['globals']['g_playerCard'][1]
    root = fields(s, rootref)
    orgs = flat(s, root['m_org'], 13)
    require(len(orgs) == 10, '仅支持第一部的十阵营存档。')
    owned = {}
    for org_id, ref in enumerate(orgs, 1):
        org = fields(s, ref)
        ids = []
        for c in flat(s, org['m_card'], 13):
            v = fields(s, c)
            ident = text(s, v['<Id>'])
            require(ident not in owned, '存档包含重复卡牌记录，请先核对。')
            owned[ident] = (org_id, c, v['m_count'])
            ids.append(ident.encode(s['encoding']))
        require(ids == sorted(ids), '原存档卡牌列表排序异常。')
    characters = {}
    for i, r in enumerate(s['records']):
        if r['sid'] >= 0 and s['defs'][r['sid']]['name'] == 'Character':
            v = fields(s, i)
            name = text(s, v['m_id'])
            require(name not in characters, '角色记录重复。')
            characters[name] = (i, v)
    pending = set()
    for name in ['m_stock', 'm_extraCard', 'm_card']:
        for ref in flat(s, root[name], 13):
            pending.add(text(s, fields(s, ref)['<Id>']))
    return rootref, orgs, owned, characters, pending


def displayable(row):
    """Formal collection cards across both parts, including items and generics."""
    return (row['種別'] in CARD_KINDS and row['出现'] in (1, 2, 3) and row['削除'] == 0
            and 1 <= row['所属'] <= 10 and not row['Id'].startswith(('测试', 'テスト')))


def eligible(row, chars, skills):
    return (displayable(row)
            and all(row[n] == 0 or row[n] in skills for n in ['技能１', '技能２']))


def initial_star(s, cap=200):
    bonus = fields(s, s['globals']['g_clearPointBonus'][1])
    values = [fields(s, ref) for ref in flat(s, bonus['m_bonus'], 13)]
    return min(cap, sum(v['<Value>'] for v in values if v['<IsUse>'] and v['<Type>'] == 3))


def card_star(s, row, chars):
    if row['種別'] == 10:
        common = fields(s, s['globals']['g_playerCommonParam'][1])
        return common['<ItemStar>'] * (2 if common['m_itemStarUp'] else 1)
    return chars[row['识别名']][1]['m_star'] if row['识别名'] in chars else initial_star(s)


def ensure_character(s, name, chars, changed_arrays, data):
    """Mirror addCharacter / CharacterCollection.Create used by native card addition."""
    if name in chars:
        return chars[name]
    save_compat.require_rule(data, 'characters')
    save_compat.validate_save(s, scope='character_write')
    import character_data
    info = character_data.load()
    root = info.get('character_root', '识别名情报')
    leaf = '事件' if root == '识别名情报' else 'イベント'
    from training import next_exp
    ident = addstr(s, name)
    replay = addrecord(s, 'CharacterEventCollection', {
        '<Id>': ident, 'm_key': addstr(s, root + '.' + name + '.' + leaf)})
    food = addrecord(s, 'FoodTicketEvent', {
        'm_id': ident, 'm_eventStage': 0, 'm_exBaseKey': addstr(s, root + '.' + name)})
    star = initial_star(s, min(200, info['star_cap']))
    ref = addrecord(s, 'Character', {'m_id': ident, 'm_star': star, '<Exp>': 0,
        '<NextExp>': next_exp(star), '<ReplayEvent>': replay, '<FoodTicketEvent>': food,
        '<IsFinishAttack>': 0})
    pool = fields(s, s['globals']['g_character'][1])['m_character']
    refs = flat(s, pool, 13)
    keys = [text(s, fields(s, r)['m_id']).encode(s['encoding']) for r in refs]
    require(keys == sorted(keys), '原角色列表排序异常。')
    refs.insert(bisect.bisect_left(keys, name.encode(s['encoding'])), ref)
    resize(s, pool)
    changed_arrays.add(pool)
    chars[name] = (ref, fields(s, ref))
    return chars[name]


def inspect(path):
    path = Path(path)
    s = parse(path.read_bytes(), str(path))
    save_compat.validate_save(s, scope='cards')
    meta = metadata(s)
    rootref, orgs, owned, chars, pending = collection(s)
    table, skills = catalog()
    require(set(owned).issubset(table), '存档中有卡牌不在当前游戏卡表内，请核对游戏与存档目录，或重新准备图鉴。')
    data = catalog_data()
    try:
        groups = save_compat.rules(data)
        rule_error = ''
    except ValueError as exc:
        groups, rule_error = {}, str(exc)
    try:
        import character_data
        character_info = character_data.load()
    except ValueError:
        character_info = None
    try:
        item_info = json.loads(app_paths.ITEM_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        item_info = {}
    rows = []
    for ident, row in table.items():
        if not displayable(row):
            continue
        skillrows = [skills.get(row[n], {}) for n in ['技能１', '技能２']]
        available = eligible(row, chars, skills) and groups.get('cards', False)
        new_character = row['识别名'] not in chars
        if new_character:
            available = available and groups.get('characters', False) and character_info is not None
        star = card_star(s, row, chars)
        # PlayerCard.RareType uses SR=0 / 87 / other for Normal / Rare / UltraRare.
        rarity = '普通' if row['ＳＲ'] == 0 else ('特级' if row['ＳＲ'] == 87 else '超稀有')
        reason = '' if available else (rule_error or ('创建新人物需要更新本机人物资料。' if new_character and character_info is None
            else '当前卡牌的技能或初始化规则尚未适配，可查看图鉴。'))
        rows.append(dict(id=ident, character=row['识别名'], org=row['所属'], faction=ORG_NAMES[row['所属']],
                         hp=row['ＨＰ'], atk=row['ＡＴＫ'], star=star, rarity=rarity, appearance=row['出现'],
                         kind=CARD_KINDS[row['種別']], new_character=row['识别名'] not in chars,
                         description='\n'.join(item_info.get(ident, [])),
                         nude=bool(row['裸']),
                         available=available, unavailable_reason=reason,
                         basic=bool(re.fullmatch(r'Lv\d+ ' + re.escape(row['识别名']), ident)),
                         owned=ident in owned or ident in pending,
                         copies=owned.get(ident, (0, 0, 0))[2],
                         skills=' / '.join(x.get('名称', '无') for x in skillrows),
                         details='\n\n'.join('%s（AP %s）\n%s' %
                             (x.get('名称', '无技能'), x.get('ＡＰ', '-'),
                              re.sub(r'r(?=[\u3000◆])', '\n', x.get('说明', ''))) for x in skillrows)))
    return dict(path=str(path), sha=sha(s['raw']), slot=meta['slot'], time=meta['time'],
                comment=meta['comment'], count=len(owned), upgrades=sum(x[2] - 1 for x in owned.values()),
                manual=meta['slot'] < 5000, pending=len(pending), cards=rows,
                factions=[dict(id=i, name=ORG_NAMES[i], count=sum(x[0] == i for x in owned.values()))
                          for i in range(1, 11)])


def list_saves(save_dir=None):
    save_dir = Path(save_dir) if save_dir is not None else settings.save_dir()
    result = []
    for path in Path(save_dir).glob('LocalSave*.asd'):
        if not re.fullmatch(r'LocalSave\d+\.asd', path.name):
            continue
        try:
            s = parse(path.read_bytes(), str(path))
            m = metadata(s)
            count = len(collection(s)[2])
            result.append(dict(path=str(path), slot=m['slot'], time=m['time'], comment=m['comment'],
                               count=count, manual=m['slot'] < 5000, mtime=path.stat().st_mtime))
        except Exception as exc:
            result.append(dict(path=str(path), slot=-1, time='', comment=str(exc), count=0,
                               manual=False, mtime=path.stat().st_mtime, error=True))
    return sorted(result, key=lambda x: x['mtime'], reverse=True)


def suggest(context, target=200, selected=()):
    """Balance factions, prefer basic versions of characters already held."""
    need = max(0, target - context['count'] - len(selected))
    chosen = set(selected)
    owned_chars = {r['character'] for r in context['cards'] if r['owned']}
    candidates = [r for r in context['cards'] if r['basic'] and r.get('appearance', 1) == 1 and r.get('available', True)
                  and not r['owned'] and r['id'] not in chosen]
    counts = {f['id']: f['count'] for f in context['factions']}
    for r in context['cards']:
        if r['id'] in chosen:
            counts[r['org']] += 1
    additions = []
    seen_chars = set()
    while need and candidates:
        candidates.sort(key=lambda r: (r['character'] not in owned_chars, r['character'] in seen_chars,
                                       counts[r['org']], int(re.match(r'Lv(\d+)', r['id'])[1]), r['id']))
        r = candidates.pop(0)
        additions.append(r['id'])
        counts[r['org']] += 1
        seen_chars.add(r['character'])
        need -= 1
    return additions


def prepare(path, identifiers, expected_sha):
    path = Path(path)
    raw = path.read_bytes()
    require(sha(raw) == expected_sha, '这个存档已被游戏更新，请刷新并重新选择。没有覆盖。')
    original = parse(raw, str(path))
    require(metadata(original)['slot'] < 5000, '自动存档仅供查看。请先保存到一个手动存档位。')
    require(identifiers and len(set(identifiers)) == len(identifiers), '选择数量无效或重复。')
    s = copy.deepcopy(original)
    require(build_payload(s, original) == original['payload'], '原存档无修改重建校验失败。')
    rootref, orgs, owned, chars, pending = collection(s)
    require(not pending, '当前存档仍有未处理卡牌，请完成宝箱选卡并重新保存后使用。')
    data = catalog_data()
    save_compat.require_rule(data, 'cards')
    save_compat.validate_save(s, exact=['PlayerCard', 'PlayerCardSkill'], scope='cards')
    save_compat.validate_save(s, scope='card_write')
    table, skills = {r['Id']: r for r in data['cards']}, {r['Id']: r for r in data['skills']}
    require(set(owned).issubset(table), '存档与本机卡表不匹配，请核对游戏与存档目录。')
    report, changed_arrays, allowed_kv = [], set(), set()
    for ident in identifiers:
        require(ident in table and eligible(table[ident], chars, skills), '当前不支持这张卡：' + ident)
        require(ident not in owned, '这张卡已经持有：' + ident)
        row = table[ident]
        orgref = orgs[row['所属'] - 1]
        org = fields(s, orgref)
        cards = flat(s, org['m_card'], 13)
        character_ref, character = ensure_character(s, row['识别名'], chars, changed_arrays, data)
        ident_index = addstr(s, ident)
        skillrefs = [addrecord(s, 'PlayerCardSkill', {'m_cardId': ident_index, '': -1,
                     '<Index>': idx, 'UsedCount': 0}) for idx in range(2)]
        skillarray = len(s['arrays'])
        s['arrays'].append({'rank': 1, 'dims': [2], 'flat': [{'type': 13, 'values': skillrefs}]})
        next_index = max([fields(s, r)['Index'] for r in cards] + [-1]) + 1
        unique = org['m_uniqueId'] + 1
        require(unique not in [fields(s, r)['UniqueId'] for r in cards], '卡牌编号冲突。')
        newref = addrecord(s, 'PlayerCard', {'m_totalAtk': 0, 'm_totalHp': 0, 'm_lastStar': -1,
                          'm_lastCount': -1, 'm_dummyStar': -1, 'm_tempStar': -1, 'm_count': 1,
                          'm_skill': skillarray, '': 0, '<Id>': ident_index, 'Index': next_index,
                          'SortedIndex': 0, 'UniqueId': unique})
        encoded = [text(s, fields(s, r)['<Id>']).encode(s['encoding']) for r in cards]
        cards.insert(bisect.bisect_left(encoded, ident.encode(s['encoding'])), newref)
        resize(s, org['m_card'])
        changed_arrays.add(org['m_card'])
        charids = flat(s, org['m_characterId'], 12)
        if row['识别名'] not in [text(s, x) for x in charids]:
            charids.append(character['m_id'])
        charids.sort(key=lambda x: text(s, x).encode(s['encoding']))
        resize(s, org['m_characterId'])
        changed_arrays.add(org['m_characterId'])
        for name, value in [('m_uniqueId', unique), ('m_isChanged', 1)]:
            index = field_index(s, orgref, name)
            allowed_kv.add(index)
            s['kv'][index] = value
        # The native Add method retains the largest leader-slot bonus (effect 142).
        ratio_idx = field_index(s, rootref, '<LeaderRatio>')
        for name in ['技能１', '技能２']:
            skill = skills.get(row[name], {})
            for suffix in ['１', '２', '３']:
                if skill.get('效果' + suffix) == 142:
                    s['kv'][ratio_idx] = max(s['kv'][ratio_idx], skill['数值' + suffix])
                    allowed_kv.add(ratio_idx)
        report.append(dict(card=ident, faction=ORG_NAMES[row['所属']], card_ref=newref,
                           character_ref=character_ref, star=card_star(s, row, chars), skill_refs=skillrefs))
        owned[ident] = (row['所属'], newref, 1)
    changed_kv = {i for i, (a, b) in enumerate(zip(original['kv'], s['kv'])) if a != b}
    require(changed_kv <= allowed_kv, '检测到预期外的字段变化。')
    require(s['records'][:len(original['records'])] == original['records'], '原记录发生变化。')
    for i, a in enumerate(original['arrays']):
        require(i in changed_arrays or a == s['arrays'][i], '无关数组发生变化。')
    payload = build_payload(s, original)
    output = raw[:4] + pack(len(payload)) + zlib.compress(payload, 1)
    check = parse(output, str(path))
    for key in ['records', 'kv', 'strings', 'globals', 'defs', 'arrays']:
        require(check[key] == s[key], '重建内容校验失败：' + key)
    require(metadata(check)['raw'] == metadata(original)['raw'], '存档说明被改变。')
    h1, h2 = original['header'], check['header']
    require(check['payload'][h2[12] + h2[13] * 4:] == original['payload'][h1[12] + h1[13] * 4:],
            '存档附加数据被改变。')
    after = collection(check)[2]
    before_count = len(collection(original)[2])
    require(len(after) == before_count + len(identifiers), '添加后的卡牌总数不符合预期。')
    for item in report:
        require(after[item['card']][1] == item['card_ref'], '新卡引用校验失败。')
        if item['character_ref'] < len(original['records']):
            require(fields(check, item['character_ref']) == fields(original, item['character_ref']),
                    '角色培养或事件数据被改变。')
        require(flat(check, fields(check, item['card_ref'])['m_skill'], 13) == item['skill_refs'],
                '新卡技能引用无效。')
    save_compat.verify_source(data)
    return output, dict(source=str(path), original_sha256=sha(raw), modified_sha256=sha(output),
                        before_count=before_count, after_count=len(after), cards=report,
                        metadata_valid=True, checked=True, installed=False)


def apply(path, identifiers, expected_sha, backup_dir=None):
    require(Path(path).resolve().parent == settings.save_dir().resolve(), '存档目录已经改变，请刷新目标存档。')
    output, report = prepare(path, identifiers, expected_sha)
    return install(path, expected_sha, output, report, '卡牌扩充', backup_dir)


def install(path, expected_sha, output, report, label, backup_dir=None):
    """Install only a validated edit, with a verified original and race checks."""
    backup_dir = Path(backup_dir) if backup_dir is not None else settings.backup_dir()
    path = Path(path)
    require(path.resolve().parent == settings.save_dir().resolve(), '存档目录已经改变，请刷新目标存档。')
    require(re.fullmatch(r'LocalSave\d+\.asd', path.name) is not None, '请选择正式手动存档。')
    require(report.get('checked') is True and report.get('original_sha256') == expected_sha
            and report.get('modified_sha256') == sha(output), '修改内容校验失败。')
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = Path(backup_dir) / (stamp + '_' + label + '_' + path.stem)
    backup.mkdir(parents=True, exist_ok=False)
    source = path.read_bytes()
    require(sha(source) == expected_sha, '存档刚刚更新，已停止写入。请刷新。')
    original_backup = backup / path.name
    original_backup.write_bytes(source)
    require(sha(original_backup.read_bytes()) == expected_sha, '备份校验失败。')
    thumb = path.parent / ('Thumb%04d.qnt' % metadata(parse(source, str(path)))['slot'])
    if thumb.exists():
        shutil.copy2(thumb, backup / thumb.name)
    (backup / '修改后的存档.asd').write_bytes(output)
    report['backup'] = str(backup)
    recordfile = backup / '修改记录.json'
    recordfile.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.cardtmp')
    try:
        temp.write_bytes(output)
        require(sha(temp.read_bytes()) == report['modified_sha256'], '临时存档校验失败。')
        require(sha(path.read_bytes()) == expected_sha, '写入前存档已变化，没有覆盖，请刷新。')
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    require(sha(path.read_bytes()) == report['modified_sha256'], '写入后的存档已再次变化。')
    report['installed'] = True
    recordfile.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (backup / '恢复说明.txt').write_text(
        '原档：' + str(original_backup) + '\n目标：' + str(path) +
        '\n需要恢复时先关闭游戏，将原档复制回目标位置，再重新进入读档菜单。\n'
        '恢复会回到修改前的进度；请勿覆盖之后的新进度。\n', encoding='utf-8-sig')
    return report
