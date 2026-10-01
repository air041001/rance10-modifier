"""Build a local card library from the user's game; ship no game art or catalog."""
from pathlib import Path
import concurrent.futures
import hashlib
import io
import json
import re
import subprocess
import tempfile
import time
import os
import urllib.request
import uuid
import zipfile
from PIL import Image
import app_paths
import game_profile as profile


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _csv_values(text):
    fields, start, quoted, escaped = [], 0, False, False
    for i, char in enumerate(text):
        if escaped:
            escaped = False
        elif quoted and char == '\\':
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == ',' and not quoted:
            fields.append(text[start:i].strip())
            start = i + 1
    if quoted:
        raise ValueError('卡牌表字符串不完整。')
    fields.append(text[start:].strip())
    return fields


def parse_table(text, name):
    start = text.find('table ' + name + ' = {')
    if start < 0:
        raise ValueError('缺少卡牌数据表：' + name)
    end = text.find('\n};', start)
    if end < 0:
        raise ValueError('卡牌表没有结束。')
    rows = text[start:end].splitlines()[1:]
    header = rows.pop(0).strip().removesuffix(',').strip()
    if not header.startswith('{') or not header.endswith('}'):
        raise ValueError('卡牌表头无效。')
    columns = []
    for field in _csv_values(header[1:-1]):
        match = re.fullmatch(r'(?:indexed\s+)?(int|string|float)\s+([^\s=]+)(?:\s*=\s*.+)?', field)
        if not match:
            raise ValueError('不支持的卡牌字段。')
        columns.append((match[2], match[1]))
    result = []
    for line in rows:
        line = line.strip().removesuffix(',').strip()
        if not line:
            continue
        if not line.startswith('{') or not line.endswith('}'):
            raise ValueError('卡牌数据行无效。')
        values = _csv_values(line[1:-1])
        if len(values) != len(columns):
            raise ValueError('卡牌字段数量不匹配。')
        data = {}
        for (key, kind), value in zip(columns, values):
            data[key] = json.loads(value) if kind == 'string' else (int(value) if kind == 'int' else float(value))
        result.append(data)
    return result


def parse_catalog(text):
    data = dict(cards=parse_table(text, '卡牌数据'), skills=parse_table(text, '技能数据'))
    validate_catalog(data)
    return data


def validate_catalog(data):
    try:
        valid = len(data['cards']) == 1134 and len(data['skills']) == 1028 and profile.catalog_digest(data) == profile.CATALOG_DIGEST
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError('卡牌数据与已验证版本不一致，请重新准备图鉴。')


def ensure_component(local_path='', allow_download=False, progress=lambda message: None):
    cached = app_paths.COMPONENT_DIR / ('alice-' + profile.ALICE_VERSION + '.exe')
    candidates = ([Path(local_path)] if local_path else []) + [cached]
    for candidate in candidates:
        if candidate.is_file():
            if _sha(candidate.read_bytes()) != profile.ALICE_SHA256:
                raise ValueError('解包组件版本不匹配；请使用官方 alice-tools 0.13.0 的 alice.exe。')
            return candidate
    if not allow_download:
        raise ValueError('请下载图鉴组件，或选择本地 alice.exe 后再准备图鉴。')
    progress('正在从官方 GitHub 获取图鉴组件…')
    request = urllib.request.Request(profile.ALICE_URL, headers={'User-Agent': 'Rance10Modifier/' + profile.VERSION})
    buffer = io.BytesIO()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            total = int(response.headers.get('Content-Length', '0'))
            previous = 0
            while chunk := response.read(256 * 1024):
                buffer.write(chunk)
                if buffer.tell() > 64 * 1024 * 1024:
                    raise ValueError('组件下载内容超过预期，已停止。')
                if buffer.tell() - previous >= 2 * 1024 * 1024:
                    previous = buffer.tell()
                    progress('正在下载图鉴组件：%.1f / %.1f MB' % (buffer.tell() / 1048576, total / 1048576))
    except OSError:
        # Use Windows' HTTPS implementation when the bundled OpenSSL handshake fails.
        buffer = io.BytesIO(_download_windows(progress))
    with zipfile.ZipFile(buffer) as archive:
        data = archive.read('alice-tools-0.13.0/alice.exe')
        license_text = archive.read('alice-tools-0.13.0/COPYING.txt')
    if _sha(data) != profile.ALICE_SHA256:
        raise ValueError('组件校验失败，已停止安装。')
    app_paths.initialize()
    temp = cached.with_suffix('.tmp')
    temp.write_bytes(data)
    temp.replace(cached)
    (app_paths.COMPONENT_DIR / 'alice-tools-COPYING.txt').write_bytes(license_text)
    return cached


def _download_windows(progress):
    curl = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32/curl.exe'
    if not curl.is_file():
        raise ValueError('无法下载官方组件。请检查网络，或从官方发布页下载 alice.exe 后选择本地组件。')
    progress('正在重新连接官方组件下载…')
    app_paths.initialize()
    with tempfile.TemporaryDirectory(prefix='download-', dir=app_paths.COMPONENT_DIR) as folder:
        folder = Path(folder)
        target, errors = folder / 'component.zip', folder / 'errors.txt'
        started, previous = time.monotonic(), 0
        with errors.open('wb') as stderr:
            process = subprocess.Popen([str(curl), '--fail', '--location', '--silent', '--show-error',
                '--proto', '=https', '--proto-redir', '=https', '--connect-timeout', '20',
                '--max-time', '120', '--max-filesize', str(64 * 1024 * 1024),
                '--output', str(target), profile.ALICE_URL], stdout=subprocess.DEVNULL, stderr=stderr,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                while process.poll() is None:
                    size = target.stat().st_size if target.exists() else 0
                    if size > 64 * 1024 * 1024 or time.monotonic() - started > 125:
                        raise ValueError('官方组件下载超时或超过预期大小，请检查网络后重试，或选择本地组件。')
                    if size - previous >= 2 * 1024 * 1024:
                        previous = size
                        progress('正在下载图鉴组件：%.1f MB' % (size / 1048576))
                    time.sleep(.2)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
        if process.returncode or not target.is_file():
            raise ValueError('无法下载官方组件。请检查网络，或从官方发布页下载 alice.exe 后选择本地组件。')
        return target.read_bytes()


def _run(tool, args, timeout=90):
    result = subprocess.run([str(tool)] + [str(arg) for arg in args], capture_output=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=timeout)
    if result.returncode:
        raise ValueError('读取游戏资源失败：' + result.stderr.decode('utf-8', errors='replace')[-400:])
    return result.stdout.decode('utf-8', errors='strict')


def cached_images():
    """Return reusable generated cards, including checking the actual PNG files."""
    try:
        entries = json.loads((app_paths.IMAGE_DIR / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(entries, dict):
        return {}
    result = {}
    for ident, entry in entries.items():
        if not isinstance(entry, dict) or entry.get('file') != _sha(ident.encode('utf-8'))[:24] + '.png':
            continue
        try:
            with Image.open(app_paths.IMAGE_DIR / entry['file']) as image:
                if image.format != 'PNG' or image.size != (208, 312):
                    continue
                image.verify()
        except (OSError, ValueError):
            continue
        result[ident] = entry
    return result


def library_status():
    import engine
    table, _ = engine.catalog()
    expected = {ident for ident, row in table.items() if engine.displayable(row)}
    ready = expected.intersection(cached_images())
    return dict(expected=len(expected), ready=len(ready), missing=len(expected - ready))


def prepare_library(game, local_tool='', allow_download=False, progress=lambda message: None):
    import engine
    game = Path(game)
    engine.validate_game(game)
    tool = ensure_component(local_tool, allow_download, progress)
    encoding = ['--input-encoding', 'CP936', '--output-encoding', 'UTF-8']
    app_paths.initialize()
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=app_paths.CACHE_DIR) as work:
        work = Path(work)
        dump = work / 'catalog.x'
        progress('正在读取游戏中的卡牌和技能数据…')
        _run(tool, ['ex', 'dump'] + encoding + ['-o', dump, game / 'Rance10EX.ex'])
        source_text = dump.read_text(encoding='utf-8')
        data = parse_catalog(source_text)
        import character_data
        character_info = character_data.parse(source_text)
        assets = {}
        archives = []
        for path in game.glob('Rance10CG*.afa'):
            match = re.fullmatch(r'Rance10CG(\d*)\.afa', path.name)
            if match:
                archives.append((int(match[1] or '1'), path))
        for _, archive in sorted(archives):
            progress('正在查找卡面：' + archive.name)
            listing = _run(tool, ['ar', 'list'] + encoding + [archive])
            for line in listing.splitlines():
                match = re.fullmatch(r'(\d+): (.+)', line)
                if match:
                    assets[match[2]] = dict(index=int(match[1]), archive=archive)

        entries, missing = {}, []
        for row in data['cards']:
            if not engine.displayable(row):
                continue
            name = next((name for ext in ['.ajp', '.qnt', '.dcf', '.webp', '.png']
                         if (name := '卡牌／' + row['ＣＧ名'] + ext) in assets), None)
            if not name:
                missing.append(row['Id'])
                continue
            entries[row['Id']] = dict(asset=name, cg=row['ＣＧ名'], faction=engine.ORG_NAMES[row['所属']])
        cached = cached_images()
        reused = {ident: cached[ident] for ident, row in entries.items()
                  if ident in cached and cached[ident].get('cg') == row['cg']
                  and cached[ident].get('source') == row['asset']
                  and cached[ident].get('faction') == row['faction']}
        pending = {ident: row for ident, row in entries.items() if ident not in reused}
        needed = {row['asset'] for row in pending.values()}
        frames = {}
        for faction in {row['faction'] for row in pending.values()}:
            resource = 'ＪＡＰＡＮ' if faction == 'JAPAN' else faction
            names = ['シス／卡牌／%s／%s所属.ajp' % (part, resource) for part in ['下地', '枠']]
            if all(name in assets for name in names):
                frames[faction] = names
                needed.update(names)

        def extract(name):
            output = work / (_sha(name.encode('utf-8'))[:24] + '.png')
            source = assets[name]
            _run(tool, ['ar', 'extract'] + encoding + ['-i', source['index'], '-o', output, source['archive']])
            with Image.open(output) as image:
                image.verify()
            return name, output

        extracted = {}
        progress('保留已有 %d 张卡面，正在补齐 %d 张…' % (len(reused), len(pending)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for i, (name, path) in enumerate(pool.map(extract, sorted(needed)), 1):
                extracted[name] = path
                if i % 30 == 0:
                    progress('正在生成卡面：%d / %d' % (i, len(needed)))
        manifest = dict(reused)
        for ident, row in pending.items():
            with Image.open(extracted[row['asset']]) as art:
                card = Image.new('RGBA', (208, 312), '#e8eef6')
                if row['faction'] in frames:
                    pair = frames[row['faction']]
                    with Image.open(extracted[pair[0]]) as bg:
                        card = bg.convert('RGBA')
                if card.size != (208, 312) or art.size != (208, 312):
                    raise ValueError('卡面尺寸不匹配，已停止准备。')
                card.alpha_composite(art.convert('RGBA'))
                if row['faction'] in frames:
                    with Image.open(extracted[pair[1]]) as border:
                        card.alpha_composite(border.convert('RGBA'))
                filename = _sha(ident.encode('utf-8'))[:24] + '.png'
                card.save(app_paths.IMAGE_DIR / filename, optimize=True)
                manifest[ident] = dict(file=filename, cg=row['cg'], source=row['asset'], faction=row['faction'])
        # Install only after generation and data validation succeed.
        for path, value in [(app_paths.CATALOG_FILE, data), (app_paths.IMAGE_DIR / 'manifest.json', manifest)]:
            temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
            temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(path)
        character_data.store(character_info)
        return dict(cards=len(manifest), missing_images=len(missing),
                    generated=len(pending), reused=len(reused))
