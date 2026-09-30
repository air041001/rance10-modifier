from pathlib import Path
import ctypes
import os
import sys
from game_profile import PROFILE_ID

RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent / 'resources'))
DATA_DIR = Path(os.environ.get('RANCE10_MODIFIER_DATA_DIR') or
                str(Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Rance10Modifier'))
CACHE_DIR = DATA_DIR / 'cache' / PROFILE_ID
CONFIG_FILE = DATA_DIR / 'settings.json'
LOG_FILE = DATA_DIR / 'operations.jsonl'
ERROR_FILE = DATA_DIR / 'last-error.txt'
CATALOG_FILE = CACHE_DIR / 'catalog.json'
CHARACTER_FILE = CACHE_DIR / 'character-info.json'
IMAGE_DIR = CACHE_DIR / 'cards'
COMPONENT_DIR = DATA_DIR / 'components'


def initialize():
    for path in [DATA_DIR, CACHE_DIR, IMAGE_DIR, COMPONENT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def documents_dir():
    if os.name == 'nt':
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return Path(buffer.value)
    return Path.home() / 'Documents'


def default_save_dir():
    base = documents_dir() / 'AliceSoft'
    candidates = [base / name / 'SaveData' for name in ['兰斯10', 'ランス10', 'Rance10']]
    return next((path for path in candidates if path.is_dir()), candidates[0])
