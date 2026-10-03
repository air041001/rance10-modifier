"""Feature checks for save edits; independent of the executable's memory layout."""
import hashlib
import json
import re
from pathlib import Path
import app_paths
import settings
import game_profile

ENCODINGS = {'CP936': 'gbk', 'CP932': 'cp932'}
SCHEMAS = {
    'PlayerCard': [(10, n) for n in ['m_totalAtk', 'm_totalHp', 'm_lastStar', 'm_lastCount',
        'm_dummyStar', 'm_tempStar', 'm_count']] + [(79, 'm_skill'), (63, ''), (12, '<Id>')] +
        [(10, n) for n in ['Index', 'SortedIndex', 'UniqueId']],
    'PlayerCardSkill': [(12, 'm_cardId'), (21, ''), (10, '<Index>'), (10, 'UsedCount')],
    'Character': [(12, 'm_id'), (10, 'm_star'), (10, '<Exp>'), (10, '<NextExp>'),
        (13, '<ReplayEvent>'), (13, '<FoodTicketEvent>'), (47, '<IsFinishAttack>')],
    'CharacterEventCollection': [(12, '<Id>'), (12, 'm_key')],
    'FoodTicketEvent': [(12, 'm_id'), (10, 'm_eventStage'), (12, 'm_exBaseKey')],
    'PlayerCardCollection': [(79, 'm_org'), (79, 'm_stock'), (79, 'm_extraCard'),
        (63, ''), (10, '<LeaderRatio>'), (79, 'm_card')],
    'OrganizationCardCollection': [(79, 'm_card'), (79, 'm_characterId'), (10, 'm_uniqueId'),
        (13, 'm_status'), (10, 'm_hp'), (10, 'm_atk'), (47, 'm_isChanged'), (79, ''), (63, '')],
    'CharacterCollection': [(79, 'm_character')],
    'ClearPointBonusCollection': [(79, 'm_bonus')],
    'ClearPointBonus': [(47, '<IsUse>'), (92, '<Type>'), (10, '<Value>')],
    'PlayerCommonParam': [(10, n) for n in ['m_foodTicket', 'm_honor', 'm_friendPoint',
        'm_lastHumanDead', 'm_lastHumanAlivePer']] + [(47, 'm_itemStarUp'), (12, 'm_bestFriendId')] +
        [(10, n) for n in ['<TotalExp>', '<PartyRank>', '<TreasureNotGetCount>', '<ItemStar>']] +
        [(47, '<IsUsedHannyZippo>')],
}
GROUPS = {
    'cards': ['PlayerCard@2', 'PlayerCard@0#1', 'PlayerCardSkill@2', 'PlayerCardSkill@0#1',
        'OrganizationCardCollection@Add', 'OrganizationCardCollection@FindInsertPos',
        'OrganizationCardCollection@CreateCharacterIdCache', 'PlayerCardCollection@Add', 'PlayerCardCollection@CalcLeaderRatio'],
    'characters': ['Character@2', 'Character@0#1', 'Character@Init', 'CharacterCollection@Create',
        'CharacterCollection@Add', 'addCharacter',
        'CharacterEventCollection@Init', 'FoodTicketEvent@0', 'FoodTicketEvent@Init',
        'ClearPointBonusCollection@BaseCardStarRank::get', 'Character::CalcNextExp',
        'Character@ForceSetStar', 'Character::GetMaxStar'],
    'star': ['Character::CalcNextExp', 'Character@ForceSetStar', 'Character::GetMaxStar',
        'PlayerCard@ForceRecalcStatus', 'OrganizationCardCollection@ForceRecalcStatus'],
    'enhancement': ['PlayerCard@ForceRecalcStatus', 'OrganizationCardCollection@ForceRecalcStatus'],
}


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()


def source(game, encoding):
    return dict(ex_sha256=file_hash(Path(game) / 'Rance10EX.ex'), encoding=encoding)


def verify_source(data):
    from engine import require
    actual = file_hash(settings.game_dir() / 'Rance10EX.ex')
    if data.get('schema') == 2:
        require(data.get('source', {}).get('encoding') in ENCODINGS, '图鉴编码资料无效，请重新准备图鉴。')
        require(data['source'].get('ex_sha256') == actual,
                '游戏卡牌数据已更换，请从当前游戏重新准备图鉴。已有缓存会保留。')
    else:
        require(actual == game_profile.GAME_HASHES['Rance10EX.ex'],
                '旧图鉴属于另一套游戏数据，请从当前游戏重新准备图鉴。')


def encoding():
    try:
        data = json.loads(app_paths.CATALOG_FILE.read_text(encoding='utf-8'))
        return ENCODINGS[data.get('source', {}).get('encoding', 'CP936')]
    except (OSError, ValueError, KeyError):
        return 'gbk'


def validate_save(s, exact=(), scope='read'):
    """Check types actually used by the editor, not arbitrary unrelated game objects."""
    from engine import require
    wanted = {
        'PlayerCardCollection': ['m_org', 'm_stock', 'm_extraCard', 'm_card'],
        'OrganizationCardCollection': ['m_card'],
        'PlayerCard': ['<Id>', 'm_count'], 'Character': ['m_id'],
    }
    if scope == 'cards':
        wanted.update(Character=['m_id', 'm_star'], PlayerCommonParam=['<ItemStar>', 'm_itemStarUp'],
            ClearPointBonusCollection=['m_bonus'], ClearPointBonus=['<IsUse>', '<Type>', '<Value>'])
    elif scope == 'card_write':
        wanted.update(OrganizationCardCollection=['m_card', 'm_characterId', 'm_uniqueId', 'm_isChanged'],
            PlayerCardCollection=['m_org', 'm_stock', 'm_extraCard', 'm_card', '<LeaderRatio>'])
    elif scope == 'character_write':
        wanted['CharacterCollection'] = ['m_character']
    elif scope == 'training':
        wanted.update(Character=['m_id', 'm_star', '<Exp>', '<NextExp>', '<FoodTicketEvent>'],
            FoodTicketEvent=['m_eventStage'], PlayerCard=['<Id>', 'm_count', 'm_dummyStar', 'm_tempStar'])
    elif scope in ['star', 'enhancement']:
        wanted.update(PlayerCard=['<Id>', 'm_count', 'm_lastStar'], OrganizationCardCollection=['m_card', 'm_isChanged'])
        if scope == 'star':
            wanted['Character'] = ['m_id', 'm_star', '<Exp>', '<NextExp>']
    for name in exact:
        wanted[name] = [field for _, field in SCHEMAS[name]]
    seen = {}
    for definition in s['defs']:
        name = definition['name']
        if name not in wanted:
            continue
        require(name not in seen, '存档结构定义重复：' + name)
        seen[name] = definition['fields']
        actual = dict((n, t) for t, n in definition['fields'] if n)
        require(len(actual) == sum(bool(n) for _, n in definition['fields']), '存档字段名重复：' + name)
        for typ, field in SCHEMAS[name]:
            if field and field in wanted[name]:
                require(actual.get(field) == typ, '存档字段类型尚未适配：' + name + '.' + field)
    for name in wanted:
        require(name in seen, '存档缺少所需结构：' + name)
    for name in exact:
        require(seen.get(name) == SCHEMAS[name], '新记录结构尚未适配：' + name)


def function_symbols(text):
    symbols = {}
    counts = {}
    for line in text.splitlines():
        match = re.match(r'/\* 0x([0-9a-f]+) \*/\s+.*? ([^\s(]+)\(', line)
        if match:
            name = match[2]
            ordinal = counts.get(name, 0)
            counts[name] = ordinal + 1
            symbols[int(match[1], 16)] = name + ('#%d' % ordinal if ordinal else '')
    return symbols


def normalize_code(text, symbols):
    from engine import require
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(';')]
    labels = {line[:-1]: 'L%d' % i for i, line in enumerate(line for line in lines if re.fullmatch(r'0x[0-9a-f]+:', line))}
    result = []
    for line in lines:
        if line.startswith(('FUNC ', 'ENDFUNC ', 'EOF ')):
            continue
        line = re.sub(r'0x[0-9a-f]+', lambda m: labels.get(m[0], m[0]), line)
        match = re.fullmatch(r'PUSH (\d+)', line)
        if match and int(match[1]) >= 1000:
            name = symbols.get(int(match[1]), '')
            if name.startswith(('PlayerCard', 'Character', 'OrganizationCard', 'FoodTicket', 'ClearPoint')):
                line = 'METHOD ' + name
        line = re.sub(r'^(NEW \S+) (\d+)$',
            lambda m: m[1] + ' ' + symbols.get(int(m[2]), m[2]), line)
        # Normalize translated data keys, not gameplay values or instructions.
        for before, after in [('識別名情報', '识别名情报'), ('イベント', '事件'), ('ランク上限', '级别上限')]:
            if line.startswith('S_PUSH '):
                line = line.replace(before, after)
        result.append(line)
    require(result and any(line.startswith('RETURN') for line in result),
            '未读到完整的加卡或培养规则，请检查图鉴组件后重新准备。')
    return hashlib.sha256('\n'.join(result).encode('utf-8')).hexdigest()


def event_paths(methods):
    """Use actual initializer keys, including partially translated scripts."""
    values = {}
    for name in ['CharacterEventCollection@Init', 'FoodTicketEvent@Init']:
        pushes = [json.loads(m[1]) for m in re.finditer(r'^\s*S_PUSH\s+("(?:\\.|[^"\\])*")\s*$', methods.get(name, ''), re.M)]
        candidates = [s for s in pushes if s.count('%s') == 1 and '.%s' in s]
        if len(candidates) != 1:
            return {}
        values[name] = candidates[0]
    event = values['CharacterEventCollection@Init'].split('.%s.')
    food = values['FoodTicketEvent@Init']
    if len(event) != 2 or not all(event) or food != event[0] + '.%s':
        return {}
    return dict(character_root=event[0], event_leaf=event[1])


def inspect_rules(game, tool, encoding, progress=lambda message: None):
    from assets import _run
    from concurrent.futures import ThreadPoolExecutor
    from save_rule_hashes import EXPECTED
    game = Path(game)
    start_hash = file_hash(game / 'Rance10.ain')
    options = ['--input-encoding', encoding, '--output-encoding', 'UTF-8']
    symbols = function_symbols(_run(tool, ['ain', 'dump', '--functions'] + options + [game / 'Rance10.ain']))
    indices = {name: index for index, name in symbols.items()}
    names = sorted({name for group in GROUPS.values() for name in group})
    def inspect(name):
        if name not in indices:
            return name, '', ''
        text = _run(tool, ['ain', 'dump', '--function', name, '--no-macros'] + options + [game / 'Rance10.ain'])
        return name, normalize_code(text, symbols), text if name in ['CharacterEventCollection@Init', 'FoodTicketEvent@Init'] else ''
    progress('正在核对加卡和培养所需的游戏规则…')
    with ThreadPoolExecutor(max_workers=4) as pool:
        checked = list(pool.map(inspect, names))
    hashes = {name: digest for name, digest, _ in checked}
    paths = event_paths({name: text for name, _, text in checked if text})
    from engine import require
    require(start_hash == file_hash(game / 'Rance10.ain'), '游戏脚本刚刚发生变化，请重新准备图鉴。')
    groups = {group: all(hashes[name] in EXPECTED.get(name, []) for name in members)
              for group, members in GROUPS.items()}
    if groups.get('characters') and not paths:
        groups['characters'] = False
    return dict(ain_sha256=start_hash, groups=groups, event_paths=paths,
                mismatches=[name for name in names if hashes[name] not in EXPECTED.get(name, [])])


def rules(data):
    """Refresh only rule fingerprints when script text/patch changes, without rebuilding images."""
    current = file_hash(settings.game_dir() / 'Rance10.ain')
    if data.get('schema') != 2:
        if current == game_profile.GAME_HASHES['Rance10.ain']:
            data['rules'] = dict(event_paths=dict(character_root='识别名情报', event_leaf='事件'))
            return dict.fromkeys(GROUPS, True)
        raise ValueError('游戏脚本已更换，请重新准备本机图鉴以核对加卡规则。')
    info = data.get('rules', {})
    if info.get('ain_sha256') != current or (info.get('groups', {}).get('characters') and 'event_paths' not in info):
        from assets import ensure_component
        tool = ensure_component(settings.load().get('alice_path', ''))
        info = inspect_rules(settings.game_dir(), tool, data['source']['encoding'])
        data['rules'] = info
        temp = app_paths.CATALOG_FILE.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temp.replace(app_paths.CATALOG_FILE)
    return info.get('groups', {})


def require_rule(data, group):
    from engine import require
    label = {'cards': '卡牌初始化', 'characters': '新人物初始化', 'star': '人物经验', 'enhancement': '属性刷新'}[group]
    require(rules(data).get(group), '当前游戏的%s规则有变化，图鉴仍可查看；此项写入需要适配。' % label)


def report(game):
    """Shareable diagnostics: file identity and compatibility, no paths or progress."""
    from engine import validate_game_directory, catalog_data
    game = validate_game_directory(game)
    info = dict(modifier_version=game_profile.VERSION,
        files={name: file_hash(game / name) for name in game_profile.GAME_HASHES})
    version = game / 'Version.txt'
    info['game_version'] = version.read_text(encoding='utf-8-sig', errors='replace').strip()[:80] if version.is_file() else '未提供'
    try:
        from live_profile import prepare
        _, live = prepare(game)
        info['live_script_supported'] = True
        info['food_selector_supported'] = live.get('Food') is not None
        if live.get('FoodError'):
            info['food_selector_status'] = live['FoodError']
        info['live_engine_check'] = '连接时识别实际运行引擎和脚本'
    except (ValueError, OSError) as exc:
        info['live_script_supported'] = False
        info['live_status'] = str(exc)
    try:
        if game.resolve() != settings.game_dir().resolve():
            info['catalog_status'] = '所选游戏目录尚未保存，请先保存目录再准备本机图鉴。'
            return info
        data = catalog_data()
        info['catalog_encoding'] = data.get('source', {}).get('encoding', 'CP936')
        info['save_features'] = rules(data)
        info['changed_rules'] = data.get('rules', {}).get('mismatches', [])
    except (ValueError, OSError) as exc:
        info['catalog_status'] = str(exc)
    return info
