"""Remove card versions and clear a character's local data after its last version."""
import copy
from pathlib import Path
import zlib
import engine
import save_compat


# The v8 serializer represents an empty string with this value, rather than
# necessarily including an empty entry in its string table.
EMPTY_STRING = 0x7fffffff


def string(s, index):
    return '' if index == EMPTY_STRING else engine.text(s, index)


def same_character(context, ident):
    row = next((r for r in context['cards'] if r['id'] == ident), None)
    if not row or row['kind'] == '物品':
        return []
    return [r['id'] for r in context['cards']
            if r['owned'] and r['character'] == row['character'] and r['kind'] != '物品']


def prepare(path, identifiers, expected_sha):
    path = Path(path)
    raw = path.read_bytes()
    engine.require(engine.sha(raw) == expected_sha, '这个存档已被游戏更新，请刷新并重新选择。没有覆盖。')
    original = engine.parse(raw, str(path))
    engine.require(engine.metadata(original)['slot'] < 5000, '自动存档仅供查看，请选择手动存档。')
    engine.require(identifiers and len(set(identifiers)) == len(identifiers), '请选择要删除的卡牌，不能重复选择。')
    s = copy.deepcopy(original)
    engine.require(engine.build_payload(s, original) == original['payload'], '原存档无修改重建校验失败。')
    _, orgs, owned, chars, pending = engine.collection(s)
    engine.require(not pending, '当前存档仍有未处理卡牌，请完成宝箱选卡并重新保存后使用。')
    data = engine.catalog_data()
    save_compat.require_rule(data, 'cards')
    save_compat.validate_save(s, scope='card_remove')
    table = {r['Id']: r for r in data['cards']}
    engine.require(set(owned) <= table.keys(), '存档与本机卡表不匹配，请重新准备图鉴。')
    selected = set(identifiers)
    engine.require(selected <= owned.keys(), '选择中有当前存档未持有的卡牌，请刷新。')
    remaining_characters = {table[ident]['识别名'] for ident in owned if ident not in selected}
    removed_characters = sorted({table[ident]['识别名'] for ident in selected} - remaining_characters)
    changed_arrays, allowed_kv = set(), set()

    def set_value(ref, name, value):
        index = engine.field_index(s, ref, name)
        allowed_kv.add(index)
        s['kv'][index] = value

    def replace_array(index, typ, values):
        engine.flat(s, index, typ)[:] = values
        engine.resize(s, index)
        changed_arrays.add(index)

    def read_array(index, typ):
        engine.require(0 <= index < len(s['arrays']), '人物记录数组引用无效。')
        array = s['arrays'][index]
        if array['rank'] == -1 and not array['flat'] and not array['dims']:
            return []
        return engine.flat(s, index, typ)

    report = [dict(card=ident, faction=engine.ORG_NAMES[owned[ident][0]],
                   copies=owned[ident][2]) for ident in identifiers]
    for org_id in sorted({owned[ident][0] for ident in selected}):
        orgref = orgs[org_id - 1]
        org = engine.fields(s, orgref)
        refs = [ref for ref in engine.flat(s, org['m_card'], 13)
                if engine.text(s, engine.fields(s, ref)['<Id>']) not in selected]
        replace_array(org['m_card'], 13, refs)
        # Native EraseInstance rebuilds this cache. Removing just the card
        # entry leaves IsExistCharacter true until the stale cache is rebuilt.
        names = {table[engine.text(s, engine.fields(s, ref)['<Id>'])]['识别名'] for ref in refs}
        charids = [engine.addstr(s, name) for name in sorted(names, key=lambda name: name.encode(s['encoding']))]
        replace_array(org['m_characterId'], 12, charids)
        # Reindex preserves the old Index order, independently of the Id-sorted
        # owning array. SortedIndex and UniqueId are not reassigned by it.
        for index, ref in enumerate(sorted(refs, key=lambda ref: engine.fields(s, ref)['Index'])):
            set_value(ref, 'Index', index)
        set_value(orgref, 'm_isChanged', 1)

    # Party ownership is also checked by character. Unset every saved leader
    # using a removed version, including slots that are currently locked.
    unset = []
    for ref, rec in enumerate(s['records']):
        if s['defs'][rec['sid']]['name'] != 'LeaderCard':
            continue
        leader = engine.fields(s, ref)
        ident = string(s, leader['m_cardId'])
        if ident not in selected:
            continue
        save_compat.validate_save(s, exact=['LeaderCard', 'CommonStatus', 'LeaderState',
            'SkillCounterValueCollection', 'SkillCounterValue'])
        for name, kind in [('m_status', 'CommonStatus'), ('m_state', 'LeaderState'),
                           ('m_skillCounter', 'SkillCounterValueCollection')]:
            target = leader[name]
            engine.fields(s, target)
            engine.require(s['defs'][s['records'][target]['sid']]['name'] == kind, '出战对象引用类型不匹配：' + name)
        for name, value in [('m_cardId', EMPTY_STRING), ('<CharacterId>', EMPTY_STRING),
                            ('<OrganizationId>', -1), ('m_hp', 0)]:
            set_value(ref, name, value)
        status = engine.fields(s, leader['m_status'])
        for name in status:
            set_value(leader['m_status'], name, 100 if name == 'StatusMaxPer' else 0)
        state = engine.fields(s, leader['m_state'])
        for name in state:
            set_value(leader['m_state'], name, -1 if name == 'm_state' else 0)
        counters = engine.fields(s, leader['m_skillCounter'])
        set_value(leader['m_skillCounter'], 'm_cardId', EMPTY_STRING)
        set_value(leader['m_skillCounter'], '<UnusedRound>', 0)
        for counter in engine.flat(s, counters['m_counter'], 13):
            for name in ['IsUsed', 'IsLastUsed', 'UsedCount']:
                set_value(counter, name, 0)
        # The unnamed saved field is the transient m_skillCache array.
        index = leader['']
        engine.require(0 <= index < len(s['arrays']), '出战技能缓存引用无效。')
        s['arrays'][index] = dict(rank=-1, dims=[], flat=[])
        changed_arrays.add(index)
        unset.append(dict(card=ident, position=leader['Index']))

    # Returning from battle / leaving a temporary fixed party can restore
    # these card IDs. Remove the deleted versions from both saved lists.
    for ref, rec in enumerate(s['records']):
        if s['defs'][rec['sid']]['name'] != 'Party':
            continue
        save_compat.validate_save(s, exact=['Party'])
        party = engine.fields(s, ref)
        for name in ['m_stockCardId', 'm_preBattleCardIds']:
            index = party[name]
            array = s['arrays'][index] if 0 <= index < len(s['arrays']) else None
            engine.require(array is not None, '编队历史引用无效。')
            if array['rank'] == -1 and not array['flat']:
                continue
            # These arrays describe slot positions: retain their lengths.
            values = engine.flat(s, index, 12)
            if any(string(s, value) in selected for value in values):
                replace_array(index, 12, [EMPTY_STRING if string(s, value) in selected else value for value in values])

    # Last-version deletion also removes the character from the owning pool.
    # Clear its local progress, but retain stable record indices for references
    # elsewhere in the save. Reacquisition creates a fresh Character object.
    removed_events = []
    reset_food_refs = set()
    if removed_characters:
        save_compat.validate_save(s, scope='character_remove')
        for name in ['g_character', 'g_eventInfo', 'g_playerCommonParam', 'g_gameContext']:
            engine.require(s['globals'].get(name, (None,))[0] == 13, '存档缺少人物清理所需对象：' + name)
        poolref = s['globals']['g_character'][1]
        pool = engine.fields(s, poolref)['m_character']
        removed_refs = {chars[name][0] for name in removed_characters if name in chars}
        replace_array(pool, 13, [ref for ref in engine.flat(s, pool, 13) if ref not in removed_refs])
        from training import next_exp
        for name in removed_characters:
            if name not in chars:
                continue
            ref, character = chars[name]
            for field, value in [('m_star', 0), ('<Exp>', 0), ('<NextExp>', next_exp(0)), ('<IsFinishAttack>', 0)]:
                set_value(ref, field, value)
            foodref = character['<FoodTicketEvent>']
            engine.fields(s, foodref)
            engine.require(s['defs'][s['records'][foodref]['sid']]['name'] == 'FoodTicketEvent', '餐券人物引用类型不匹配。')
            set_value(foodref, 'm_eventStage', 0)
            reset_food_refs.add(foodref)
        eventref = s['globals']['g_eventInfo'][1]
        engine.require(s['defs'][s['records'][eventref]['sid']]['name'] == 'EventReadInfo', '个人事件集合引用类型不匹配。')
        eventarray = engine.fields(s, eventref)['m_eventName']
        events = read_array(eventarray, 12)
        prefixes = tuple(name + separator for name in removed_characters for separator in ['／', '/'])
        removed_events = [engine.text(s, value) for value in events if engine.text(s, value).startswith(prefixes)]
        if removed_events:
            replace_array(eventarray, 12, [value for value in events if not engine.text(s, value).startswith(prefixes)])
        commonref = s['globals']['g_playerCommonParam'][1]
        if string(s, engine.fields(s, commonref)['m_bestFriendId']) in removed_characters:
            set_value(commonref, 'm_bestFriendId', EMPTY_STRING)

    # Local card-show history is separate from the cross-save collection.
    # Drop deleted versions from this save so reacquisition can show them anew.
    if 'g_gameContext' in s['globals']:
        context = engine.fields(s, s['globals']['g_gameContext'][1])
        index = context.get('m_shownCardIds')
        if index is not None:
            values = read_array(index, 12)
            if any(string(s, value) in selected for value in values):
                replace_array(index, 12, [value for value in values if string(s, value) not in selected])

    changed = {i for i, (a, b) in enumerate(zip(original['kv'], s['kv'])) if a != b}
    engine.require(changed <= allowed_kv, '检测到删卡范围以外的字段变化。')
    for key in ['records', 'globals', 'defs']:
        engine.require(s[key] == original[key], '无关结构被改变：' + key)
    for i, array in enumerate(original['arrays']):
        engine.require(i in changed_arrays or s['arrays'][i] == array, '无关数组被改变。')
    for name, (ref, _) in chars.items():
        if name not in removed_characters:
            engine.require(engine.fields(s, ref) == engine.fields(original, ref), '其他人物培养数据被改变。')
    for ref, rec in enumerate(original['records']):
        if original['defs'][rec['sid']]['name'] in ['FoodTicketEvent', 'CharacterEventCollection'] and ref not in reset_food_refs:
            engine.require(engine.fields(s, ref) == engine.fields(original, ref), '人物故事记录被改变。')
    payload = engine.build_payload(s, original)
    output = raw[:4] + engine.pack(len(payload)) + zlib.compress(payload, 1)
    check = engine.parse(output, str(path))
    for key in ['records', 'arrays', 'strings', 'globals', 'defs', 'kv']:
        engine.require(check[key] == s[key], '删卡存档回读校验失败：' + key)
    engine.require(engine.metadata(check)['raw'] == engine.metadata(original)['raw'], '存档说明被改变。')
    h1, h2 = original['header'], check['header']
    engine.require(check['payload'][h2[12] + h2[13] * 4:] == original['payload'][h1[12] + h1[13] * 4:],
                   '存档附加数据被改变。')
    after = engine.collection(check)[2]
    engine.require(set(after) == set(owned) - selected, '删除后的持有卡牌不符合预期。')
    for ident, (_, ref, _) in after.items():
        before, now = engine.fields(original, ref), engine.fields(check, ref)
        engine.require(all(now[key] == value for key, value in before.items() if key != 'Index'),
                       '其他卡牌培养或技能数据被改变。')
    after_chars = engine.collection(check)[3]
    engine.require(set(after_chars) == set(chars) - set(removed_characters), '删除后的人物集合不符合预期。')
    save_compat.verify_source(data)
    return output, dict(action='remove_cards', source=str(path), original_sha256=expected_sha,
        modified_sha256=engine.sha(output), before_count=len(owned), after_count=len(after),
        cards=report, removed_characters=removed_characters, removed_personal_events=removed_events, unset_leaders=unset,
        metadata_valid=True, checked=True, installed=False)


def apply(path, identifiers, expected_sha, backup_dir=None):
    engine.require(Path(path).resolve().parent == engine.settings.save_dir().resolve(),
                   '存档目录已经改变，请刷新目标存档。')
    output, report = prepare(path, identifiers, expected_sha)
    return engine.install(path, expected_sha, output, report, '删除卡牌', backup_dir)
