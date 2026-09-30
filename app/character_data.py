"""Small local character metadata extracted from the verified game EX file."""
import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path
import app_paths
import game_profile


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')).hexdigest()


def parse(text):
    start = text.find('tree 识别名情报 = {\n')
    end = text.find('\n};', start)
    if start < 0 or end < 0:
        raise ValueError('缺少人物餐券资料。')
    characters = {}
    for match in re.finditer(r'^\t([^\s=]+) = \{\n(.*?)^\t\},', text[start:end], re.M | re.S):
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
    for key in ['级别上限', '重叠上限']:
        match = re.search(r'^int ' + key + r' = (\d+);$', text, re.M)
        if not match:
            raise ValueError('缺少游戏培养上限。')
        caps[key] = int(match[1])
    data = dict(schema=1, star_cap=caps['级别上限'], enhancement_cap=caps['重叠上限'],
                characters=characters)
    validate(data)
    return data


def validate(data):
    if digest(data) != game_profile.CHARACTER_DIGEST:
        raise ValueError('人物资料与已验证版本不一致，请在设置中更新人物资料。')


def load():
    try:
        data = json.loads(app_paths.CHARACTER_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('请先在“设置与图鉴”点击“更新人物资料”。已有卡面会保留。') from exc
    validate(data)
    return data


def store(data):
    validate(data)
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
    game = engine.validate_game(game)
    tool = ensure_component(local_tool)
    progress('正在读取人物★等级上限与餐券条件…')
    app_paths.initialize()
    with tempfile.TemporaryDirectory(prefix='characters-', dir=app_paths.CACHE_DIR) as folder:
        dump = Path(folder) / 'characters.x'
        _run(tool, ['ex', 'dump', '--input-encoding', 'CP936', '--output-encoding', 'UTF-8',
                    '-o', dump, game / 'Rance10EX.ex'])
        data = parse(dump.read_text(encoding='utf-8'))
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
