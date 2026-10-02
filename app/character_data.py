"""Small local character metadata extracted from the verified game EX file."""
import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path
import app_paths
import game_profile
import save_compat


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')).hexdigest()


def parse(text, source=None):
    root = '识别名情报' if 'tree 识别名情报 = {\n' in text else '識別名情報'
    start = text.find('tree ' + root + ' = {\n')
    end = text.find('\n};', start)
    if start < 0 or end < 0:
        raise ValueError('缺少人物餐券资料。')
    characters = {}
    for match in re.finditer(r'^\t("(?:\\.|[^"\\])*"|[^\s=]+) = \{\n(.*?)^\t\},', text[start:end], re.M | re.S):
        name, body = match.groups()
        if name.startswith('"'):
            name = json.loads(name)
        conditions = []
        for number in '１２３':
            field = re.search(r'^\t\tキャライベント' + number + r' = \(list\) \{ (.*?) \},$', body, re.M)
            if field is None:
                conditions.append('')
            else:
                from assets import _csv_values
                values = [json.loads(value) for value in _csv_values(field[1])]
                if not values or not all(isinstance(v, str) for v in values):
                    raise ValueError('餐券条件格式尚未适配。')
                # EX_AString returns the first item, as FoodTicketEvent does.
                conditions.append(values[0])
        if name in characters:
            raise ValueError('人物资料出现重复。')
        characters[name] = conditions
    caps = {}
    for key, alternatives in [('级别上限', '级别上限|ランク上限'), ('重叠上限', '重叠上限|重ね上限')]:
        match = re.search(r'^int (?:' + alternatives + r') = (\d+);$', text, re.M)
        if not match:
            raise ValueError('缺少游戏培养上限。')
        caps[key] = int(match[1])
    data = dict(schema=1, star_cap=caps['级别上限'], enhancement_cap=caps['重叠上限'],
                characters=characters)
    if source is not None:
        data.update(schema=2, source=source, character_root=root)
        data['content_digest'] = digest(data)
    validate(data, verify_source=False)
    return data


def validate(data, verify_source=True):
    if data.get('schema') == 2:
        valid = (data.get('content_digest') == digest({k: v for k, v in data.items() if k != 'content_digest'})
            and type(data.get('star_cap')) is int and data['star_cap'] > 0
            and type(data.get('enhancement_cap')) is int and data['enhancement_cap'] > 0
            and data.get('character_root') in ['识别名情报', '識別名情報']
            and isinstance(data.get('characters'), dict) and bool(data['characters'])
            and all(isinstance(name, str) and isinstance(row, list) and len(row) == 3
                    and all(isinstance(v, str) for v in row) for name, row in data['characters'].items()))
    else:
        valid = digest(data) == game_profile.CHARACTER_DIGEST
    if not valid:
        raise ValueError('人物资料结构或校验不一致，请在设置中更新人物资料。')
    if verify_source:
        save_compat.verify_source(data)


def load():
    try:
        data = json.loads(app_paths.CHARACTER_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('请先在“设置与图鉴”点击“更新人物资料”。已有卡面会保留。') from exc
    validate(data)
    return data


def store(data):
    validate(data, verify_source=False)
    app_paths.initialize()
    temp = app_paths.CHARACTER_FILE.with_name('character-info.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(app_paths.CHARACTER_FILE)
    finally:
        if temp.exists():
            temp.unlink()


def prepare(game, local_tool='', progress=lambda message: None):
    import engine
    from assets import ensure_component, _run
    game = engine.validate_game_directory(game)
    tool = ensure_component(local_tool)
    progress('正在读取人物★等级上限与餐券条件…')
    app_paths.initialize()
    with tempfile.TemporaryDirectory(prefix='characters-', dir=app_paths.CACHE_DIR) as folder:
        from assets import dump_game_ex
        ex_hash = save_compat.file_hash(game / 'Rance10EX.ex')
        text, encoding = dump_game_ex(tool, game, folder)
        data = parse(text, dict(ex_sha256=ex_hash, encoding=encoding))
        engine.require(ex_hash == save_compat.file_hash(game / 'Rance10EX.ex'),
            '游戏数据刚刚发生变化，请重新准备人物资料。')
    store(data)
    return dict(characters=len(data['characters']), star_cap=data['star_cap'],
                enhancement_cap=data['enhancement_cap'])


def story(conditions, stage):
    maximum = next((i for i, value in enumerate(conditions) if value in ['', '条件不成立']), 3)
    rows = []
    for i, condition in enumerate(conditions):
        state = '无此故事' if i >= maximum else ('已看过' if stage > i else '未看过')
        rows.append(dict(letter='ABC'[i], condition=condition, state=state))
    return dict(completed=min(stage, maximum), maximum=maximum, rows=rows,
                next_condition=conditions[stage] if stage < maximum else '',
                finished=stage >= maximum)
