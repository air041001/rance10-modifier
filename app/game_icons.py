"""Small resource sprites, cached from each user's own game archives."""
import hashlib
import json
import re
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageTk, ImageOps
import app_paths
import settings

NAMES = dict(ticket=('餐券积分', '食券ポイント'), gold=('金块积分', '金塊ポイント'),
             friend=('友情积分', '友情ポイント'))


def cache_dir(game):
    identity = hashlib.sha256(str(Path(game).resolve()).casefold().encode('utf-8')).hexdigest()[:20]
    return app_paths.CACHE_DIR / 'game-ui' / identity


def prepare_from_assets(tool, game, assets, encoding):
    import assets as library
    folder = cache_dir(game)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    try:
        manifest = json.loads((folder / 'source.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    with tempfile.TemporaryDirectory(prefix='rance-ui-') as temp:
        for kind, names in NAMES.items():
            matches = [(name, entry) for name, entry in assets.items()
                       if re.split(r'[／/\\]', name)[-1] in [n + '.ajp' for n in names]]
            if len(matches) != 1:
                continue
            name, source = matches[0]
            archive = Path(source['archive'])
            stat = archive.stat()
            identity = dict(archive=archive.name, size=stat.st_size, modified=stat.st_mtime_ns,
                            name=name, index=source['index'])
            destination = folder / (kind + '.png')
            if manifest.get(kind) == identity and destination.is_file():
                continue
            output = Path(temp) / (kind + '.png')
            library._run(tool, ['ar', 'extract'] + encoding +
                         ['-i', source['index'], '-o', output, archive])
            with Image.open(output) as image:
                if image.size != (64, 64):
                    continue
                image.convert('RGBA').save(destination)
            manifest[kind] = identity
    (folder / 'source.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')


def prepare_available(game):
    """Optional cosmetic upgrade; never download a tool or gate live features."""
    import assets as library
    try:
        tool = library.ensure_component(settings.load().get('alice_path', ''), False)
    except (OSError, ValueError):
        return
    encoding = 'CP932'
    try:
        data = json.loads(app_paths.CATALOG_FILE.read_text(encoding='utf-8'))
        encoding = data.get('source', {}).get('encoding', encoding)
    except (OSError, ValueError):
        pass
    for codec in dict.fromkeys([encoding, 'CP936', 'CP932']):
        try:
            entries = {}
            for archive in sorted(Path(game).glob('Rance10CG*.afa')):
                listing = library._run(tool, ['ar', 'list', '--input-encoding', codec,
                                              '--output-encoding', 'UTF-8', archive])
                for line in listing.splitlines():
                    match = re.fullmatch(r'(\d+): (.+)', line)
                    if match:
                        entries[match[2]] = dict(index=int(match[1]), archive=archive)
            prepare_from_assets(tool, game, entries, ['--input-encoding', codec, '--output-encoding', 'UTF-8'])
            if all((cache_dir(game) / (kind + '.png')).exists() for kind in NAMES):
                return
        except (OSError, ValueError):
            continue


class Icons:
    def __init__(self, master):
        self.master, self.cache = master, {}

    def reload(self):
        self.cache.clear()

    def get(self, kind, size=32, empty=False):
        import ui_theme
        game = settings.load().get('game_dir', '')
        key = (game, kind, size, empty, ui_theme.MODE)
        if key in self.cache:
            return self.cache[key]
        try:
            with Image.open(cache_dir(game) / (kind + '.png')) as source:
                picture = source.convert('RGBA')
        except (OSError, ValueError):
            picture = self.fallback(kind, ui_theme.BLUE)
        picture = picture.resize((size, size), Image.Resampling.LANCZOS)
        if empty:
            alpha = picture.getchannel('A').point(lambda v: int(v * .22))
            picture = ImageOps.grayscale(picture).convert('RGBA')
            picture.putalpha(alpha)
        photo = ImageTk.PhotoImage(picture, master=self.master)
        self.cache[key] = photo
        return photo

    @staticmethod
    def fallback(kind, colour):
        picture = Image.new('RGBA', (64, 64))
        pen = ImageDraw.Draw(picture)
        if kind == 'ticket':
            pen.rounded_rectangle((6, 16, 58, 48), radius=3, outline=colour, width=3)
            pen.line((43, 17, 43, 47), fill=colour, width=2)
            pen.line((15, 28, 35, 28), fill=colour, width=2)
            pen.line((15, 36, 31, 36), fill=colour, width=2)
        elif kind == 'gold':
            pen.polygon([(16, 17), (47, 17), (58, 48), (5, 48)], outline=colour, width=3)
            pen.line((17, 27, 47, 27), fill=colour, width=2)
        elif kind == 'friend':
            pen.line([(12, 20), (7, 39), (20, 46), (32, 33), (44, 46), (57, 39), (52, 20)],
                     fill=colour, width=4)
            pen.line([(12, 20), (25, 26), (32, 20), (40, 26), (52, 20)], fill=colour, width=4)
        else:
            for x, y in [(25, 12), (43, 20)]:
                pen.ellipse((x-6, y-6, x+6, y+6), fill=colour)
                pen.rounded_rectangle((x-10, y+9, x+10, y+23), radius=4, fill=colour)
        return picture
