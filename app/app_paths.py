from pathlib import Path
import ctypes
import os
import json
import shutil
import sys
from game_profile import PROFILE_ID

def documents_dir():
    if os.name == 'nt':
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return Path(buffer.value)
    return Path.home() / 'Documents'


RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent / 'resources'))
DATA_DIR = Path(os.environ.get('RANCE10_MODIFIER_DATA_DIR') or str(documents_dir() / 'Rance10Modifier'))
LEGACY_DATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Rance10Modifier'
CACHE_DIR = DATA_DIR / 'cache' / PROFILE_ID
CONFIG_FILE = DATA_DIR / 'settings.json'
LOG_FILE = DATA_DIR / 'operations.jsonl'
ERROR_FILE = DATA_DIR / 'last-error.txt'
CATALOG_FILE = CACHE_DIR / 'catalog.json'
CHARACTER_FILE = CACHE_DIR / 'character-info.json'
IMAGE_DIR = CACHE_DIR / 'cards'
COMPONENT_DIR = DATA_DIR / 'components'


def initialize():
    if not os.environ.get('RANCE10_MODIFIER_DATA_DIR'):
        migrate_legacy()
    for path in [DATA_DIR, CACHE_DIR, IMAGE_DIR, COMPONENT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def migrate_legacy():
    """Import old data once without replacing any existing destination data."""
    if CONFIG_FILE.exists() or not (LEGACY_DATA_DIR / 'settings.json').is_file():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ['cache', 'components']:
        old, new = LEGACY_DATA_DIR / name, DATA_DIR / name
        if old.is_dir():
            for source in old.rglob('*'):
                target = new / source.relative_to(old)
                if source.is_file() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    log = LEGACY_DATA_DIR / 'operations.jsonl'
    if log.is_file() and not LOG_FILE.exists():
        shutil.copy2(log, LOG_FILE)
    # Install config last so an interrupted copy can finish on the next launch.
    try:
        config = json.loads((LEGACY_DATA_DIR / 'settings.json').read_text(encoding='utf-8-sig'))
        if not isinstance(config, dict):
            return
        component = config.get('alice_path')
        if isinstance(component, str) and Path(component).parent == LEGACY_DATA_DIR / 'components':
            config['alice_path'] = str(COMPONENT_DIR / Path(component).name)
        temp = CONFIG_FILE.with_suffix('.migration.tmp')
        temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(CONFIG_FILE)
    except (ValueError, OSError):
        # A malformed legacy config never prevents opening the path picker.
        return


def default_save_dir():
    base = documents_dir() / 'AliceSoft'
    candidates = [base / name / 'SaveData' for name in ['兰斯10', 'ランス10', 'Rance10']]
    return next((path for path in candidates if path.is_dir()), candidates[0])
