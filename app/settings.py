from pathlib import Path
import json
import os
import uuid
import app_paths

_current = None


def load():
    global _current
    if _current is None:
        app_paths.initialize()
        data = {}
        if app_paths.CONFIG_FILE.exists():
            try:
                data = json.loads(app_paths.CONFIG_FILE.read_text(encoding='utf-8'))
                if not isinstance(data, dict):
                    data = {}
            except (ValueError, OSError):
                pass
        _current = {key: value for key, value in data.items()
                    if key in ['game_dir', 'save_dir', 'alice_path', 'theme'] and isinstance(value, str)}
    return dict(_current)


def game_dir():
    value = load().get('game_dir')
    if not value:
        raise ValueError('请先在“设置”中选择游戏目录。')
    return Path(value)


def save_dir():
    config = load()
    return Path(config.get('save_dir') or app_paths.default_save_dir(config.get('game_dir')))


def backup_dir():
    return save_dir().parent / '修改前备份'


def _store(data):
    global _current
    app_paths.initialize()
    temp = app_paths.CONFIG_FILE.with_name('settings.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(dict(schema=1, **data), ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, app_paths.CONFIG_FILE)
    finally:
        if temp.exists():
            temp.unlink()
    _current = data
    return data


def save(game, saves, alice=''):
    data = load()
    data.update(game_dir=str(Path(game).resolve()), save_dir=str(Path(saves).resolve()), alice_path=str(alice or ''))
    return _store(data)


def save_theme(mode):
    data = load()
    data['theme'] = mode if mode in ['dark', 'light'] else 'dark'
    return _store(data)
