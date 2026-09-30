"""Constrained cultivation edits; story flags and inventory are preserved."""
import copy
import math
import struct
import zlib
from pathlib import Path
import engine
import character_data


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def next_exp(star):
    if not isinstance(star, int) or not 0 <= star <= 200:
        raise ValueError('人物★等级应在0到200之间。')
    if star >= 100:
        return 99999
    # AIN float parameters, Math.Pow result and multiplication are 32 bit.
    return min(99999, int(f32(100 * f32(math.pow(f32(1.1), star)))))


def inspect(path):
    context = engine.inspect(path)
    s = engine.parse(Path(path).read_bytes(), str(path))
    engine.require(engine.sha(s['raw']) == context['sha'], '存档刚刚更新，请重新刷新。')
    _, _, owned, chars, pending = engine.collection(s)
    data = character_data.load()
    table, _ = engine.catalog()
    rows = []
    for ident, (org, ref, count) in owned.items():
        card = table.get(ident)
        if not card or card['種別'] != 0 or card['识别名'] not in chars:
            continue
        name = card['识别名']
        char = chars[name][1]
        values = engine.fields(s, ref)
        food = engine.fields(s, char['<FoodTicketEvent>'])
        conditions = data['characters'].get(name)
        info = character_data.story(conditions, food['m_eventStage']) if conditions is not None else None
        rows.append(dict(id=ident, character=name, faction=engine.ORG_NAMES[org], star=char['m_star'],
                         exp=char['<Exp>'], next_exp=char['<NextExp>'], enhancement=count - 1,
                         overridden=values['m_dummyStar'] >= 0 or values['m_tempStar'] >= 0,
                         story=info))
    context['training_cards'] = sorted(rows, key=lambda r: (r['faction'], r['character'], r['id']))
    context['star_cap'], context['enhancement_cap'] = data['star_cap'], data['enhancement_cap']
    return context


def prepare(path, kind, target, value, expected_sha):
    engine.require(kind in ['star', 'enhancement'], '未知培养操作。')
    engine.require(type(value) is int, '请输入整数。')
    raw = Path(path).read_bytes()
    engine.require(engine.sha(raw) == expected_sha, '这个存档已被游戏更新，请刷新。没有覆盖。')
    original = engine.parse(raw, str(path))
    meta = engine.metadata(original)
    engine.require(meta['slot'] < 5000, '自动存档仅供查看，请选择手动存档。')
    s = copy.deepcopy(original)
    engine.require(engine.build_payload(s, original) == original['payload'], '原档重建校验失败。')
    _, orgs, owned, chars, pending = engine.collection(s)
    engine.require(not pending, '请先处理宝箱选卡并重新保存，再修改培养。')
    table, _ = engine.catalog()
    limits = character_data.load()
    allowed, affected = set(), []

    def set_value(ref, name, val):
        index = engine.field_index(s, ref, name)
        allowed.add(index)
        s['kv'][index] = val

    if kind == 'star':
        engine.require(target in chars and any(table.get(ident, {}).get('识别名') == target
                       and table[ident]['種別'] == 0 for ident in owned), '请选择已经持有的人物。')
        ref, character = chars[target]
        before = character['m_star']
        engine.require(before < value <= limits['star_cap'], '★等级只能提高，最高%d。' % limits['star_cap'])
        engine.require(character['<NextExp>'] == next_exp(before), '人物经验门槛与已验证规则不一致，没有修改。')
        set_value(ref, 'm_star', value)
        set_value(ref, '<Exp>', 0)
        set_value(ref, '<NextExp>', next_exp(value))
        affected = [ident for ident in owned if table.get(ident, {}).get('识别名') == target
                    and table[ident]['種別'] == 0]
    else:
        engine.require(target in owned and table.get(target, {}).get('種別') == 0, '请选择持有的人物卡牌。')
        _, ref, count = owned[target]
        before = count - 1
        engine.require(before < value <= limits['enhancement_cap'], '强化只能提高，最高+%d。' % limits['enhancement_cap'])
        set_value(ref, 'm_count', value + 1)
        affected = [target]
    for ident in affected:
        org, card_ref, _ = owned[ident]
        # The native ForceRecalcStatus clears only m_lastStar, which forces
        # both HP and ATK to be computed again from star and copy count.
        set_value(card_ref, 'm_lastStar', -1)
        set_value(orgs[org - 1], 'm_isChanged', 1)
    changed = {i for i, (a, b) in enumerate(zip(original['kv'], s['kv'])) if a != b}
    engine.require(changed <= allowed, '检测到培养范围以外的字段变化。')
    for key in ['records', 'arrays', 'strings', 'globals', 'defs']:
        engine.require(s[key] == original[key], '无关结构被改变：' + key)
    payload = engine.build_payload(s, original)
    engine.require(len(payload) == len(original['payload']), '培养编辑改变了存档布局。')
    output = raw[:4] + engine.pack(len(payload)) + zlib.compress(payload, 1)
    check = engine.parse(output, str(path))
    for key in ['records', 'arrays', 'strings', 'globals', 'defs', 'kv']:
        engine.require(check[key] == s[key], '培养存档回读校验失败：' + key)
    h = original['header']
    engine.require(check['payload'][h[12] + h[13] * 4:] == original['payload'][h[12] + h[13] * 4:],
                   '培养编辑改变了存档附加内容。')
    engine.require(engine.metadata(check)['raw'] == meta['raw'], '存档说明被改变。')
    after_owned = engine.collection(check)[2]
    engine.require(set(after_owned) == set(owned), '持有卡牌发生变化。')
    return output, dict(source=str(path), slot=meta['slot'], action=kind, target=target,
                        before=before, after=value, affected=affected, changed_fields=len(changed),
                        original_sha256=expected_sha, modified_sha256=engine.sha(output),
                        metadata_valid=True, checked=True, installed=False)


def apply(path, kind, target, value, expected_sha, backup_dir=None):
    engine.check_version()
    # Check the configured destination before even preparing an edit.
    engine.require(Path(path).resolve().parent == engine.settings.save_dir().resolve(),
                   '存档目录已经改变，请刷新目标存档。')
    output, report = prepare(path, kind, target, value, expected_sha)
    return engine.install(path, expected_sha, output, report,
                          '人物培养' if kind == 'star' else '同卡强化', backup_dir)
