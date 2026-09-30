"""Refuse private inputs or game resources in the publishable file set."""
from pathlib import Path
import subprocess
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from game_profile import VERSION

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [s for s in subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0') if s]
    allowed = {'.py', '.cs', '.md', '.txt', '.yml', '.spec'}
    markers = ['E:' + chr(92), 'C:' + chr(92) + 'Users', 'ghp_', 'github_pat_', 'BaiduNetdiskDownload']
    for name in files:
        path = ROOT / name
        if path.suffix not in allowed and name not in ['LICENSE', '.gitignore', '.gitattributes']:
            raise ValueError('Unexpected source artifact: ' + name)
        if any(marker in path.read_text(encoding='utf-8-sig') for marker in markers):
            if name != 'scripts/audit_release.py':
                raise ValueError('Possible personal path or credential marker: ' + name)
    packages = list((ROOT / 'release').glob('Rance10Modifier-v%s-windows-x64.zip' % VERSION))
    if len(packages) != 1:
        raise ValueError('Expected one release package.')
    prohibited = ['alice.exe', 'catalog.json', 'character-info.json', 'manifest.json', 'settings.json', 'operations.jsonl', 'last-error.txt']
    forbidden = {'.asd', '.qnt', '.afa', '.ain', '.ex', '.x'}
    entries = zipfile.ZipFile(packages[0]).namelist()
    for name in entries:
        path = Path(name)
        if path.suffix.lower() in forbidden or path.name in prohibited:
            raise ValueError('Game or personal data in release: ' + name)
        if path.suffix.lower() in ['.png', '.jpg', '.webp', '.ajp', '.dcf']:
            raise ValueError('Unexpected image resource: ' + name)
    print('Source:', len(files), 'files. Release:', len(entries), 'files.')
    print('No game data, card images, personal saves, settings, or logs.')


if __name__ == '__main__':
    main()
