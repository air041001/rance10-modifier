import json
import subprocess
import tempfile
from pathlib import Path
import engine
import app_paths
import settings


def _invoke(args):
    with tempfile.TemporaryDirectory(prefix='rance-live-') as temp:
        report = Path(temp) / 'result.json'
        executable = app_paths.RESOURCE_DIR / 'LiveValues.exe'
        if not executable.is_file():
            raise ValueError('缺少运行组件，请重新解压完整程序包。')
        subprocess.run([str(executable)] + args + ['--report', str(report)], timeout=45,
                       creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if not report.exists():
            raise ValueError('运行组件未返回状态，请检查 Windows 运行环境后重新打开程序。')
        data = json.loads(report.read_text(encoding='utf-8-sig'))
        if not data.get('success'):
            raise ValueError(data.get('error', '读取失败，请刷新。'))
        return data


def discover():
    return _invoke(['--discover']).get('processes', [])


def run(action='probe', amount=None, country=None):
    if action not in ['probe', 'fill3', 'fillfriend3', 'fillbattle3', 'addbattle', 'setpoints', 'addpoints']:
        raise ValueError('不支持的操作。')
    if action in ('fillbattle3', 'addbattle'):
        if type(country) is not int or country not in range(1, 5):
            raise ValueError('请选择四国之一的战果。')
        if action == 'addbattle' and (type(amount) is not int or amount not in (-1, 1)):
            raise ValueError('战果每次增加或减少 1 点。')
    elif country is not None:
        raise ValueError('该操作不使用国家选择。')
    profile = engine.check_live_version()
    args = ['--' + action]
    if amount is not None:
        args.append(str(int(amount)))
    if country is not None:
        args += ['--country', str(country)]
    args += ['--game-dir', str(settings.game_dir()), '--runtime-profile', str(profile)]
    data = _invoke(args)
    if action != 'probe':
        app_paths.initialize()
        with app_paths.LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
    return data
