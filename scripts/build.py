"""Build a standalone Windows folder and a clean, shareable ZIP."""
from pathlib import Path
import hashlib
import importlib.metadata
import os
import shutil
import subprocess
import sys
import zipfile
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from game_profile import VERSION


def native():
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():
        raise RuntimeError('Missing Windows .NET Framework x64 C# compiler.')
    subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/optimize+',
                    '/out:' + str(ROOT / 'resources/LiveValues.exe'),
                    '/r:System.Web.Extensions.dll', '/r:System.Drawing.dll',
                    '/r:System.Windows.Forms.dll', '/r:System.Core.dll',
                    str(ROOT / 'native/LiveValues.cs')], check=True)


def licenses():
    folder = ROOT / 'resources/licenses'
    folder.mkdir(parents=True, exist_ok=True)
    found = set()
    for name in ['Pillow', 'PyInstaller', 'altgraph', 'packaging', 'pefile', 'pywin32-ctypes', 'pyinstaller-hooks-contrib']:
        distribution = importlib.metadata.distribution(name)
        for entry in distribution.files or []:
            if any(word in entry.name.lower() for word in ['license', 'copying']) and entry.suffix.lower() not in ['.py', '.pyc']:
                source = Path(distribution.locate_file(entry))
                if source.is_file():
                    shutil.copy2(source, folder / (name + '-' + entry.name))
                    found.add(name)
    base = Path(sys.base_prefix)
    python_license = base / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python license not found.')
    shutil.copy2(python_license, folder / 'Python-LICENSE.txt')
    for name in ['tcl8.6', 'tk8.6']:
        source = base / 'tcl' / name / 'license.terms'
        if name == 'tcl8.6' and not source.is_file():
            # Some official Windows Python installers omit this text file.
            source = ROOT / 'resources/Tcl-LICENSE.txt'
        if not source.is_file():
            raise RuntimeError('Missing Tcl/Tk license: ' + str(source))
        shutil.copy2(source, folder / (name + '-license.terms'))
    if not {'Pillow', 'PyInstaller'} <= found:
        raise RuntimeError('Core dependency license missing.')


def icon_and_version():
    image = Image.new('RGBA', (256, 256), '#192536')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((15, 15, 241, 241), radius=44, fill='#2b3d55')
    draw.rounded_rectangle((34, 185, 222, 199), radius=7, fill='#6c9dff')
    face = ImageFont.truetype(str(Path(os.environ['WINDIR']) / 'Fonts/segoeuib.ttf'), 112)
    draw.text((128, 105), 'RX', font=face, fill='#e8c57e', anchor='mm')
    image.save(ROOT / 'resources/app.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    parts = tuple(int(v) for v in VERSION.split('.')) + (0,)
    version = f"""VSVersionInfo(
      ffi=FixedFileInfo(filevers={parts}, prodvers={parts}, mask=0x3f, flags=0x0,
          OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
      kids=[StringFileInfo([StringTable('080404B0', [
          StringStruct('CompanyName', 'air041001'),
          StringStruct('FileDescription', '兰斯10修改器'),
          StringStruct('FileVersion', '{VERSION}'),
          StringStruct('ProductName', 'Rance10Modifier'),
          StringStruct('ProductVersion', '{VERSION}'),
          StringStruct('OriginalFilename', '兰斯10修改器.exe'),
          StringStruct('LegalCopyright', 'Copyright 2026 air041001, MIT License')
      ])]), VarFileInfo([VarStruct('Translation', [2052,1200])])])
    """
    (ROOT / 'resources/version-info.txt').write_text(version.strip() + '\n', encoding='utf-8')


def main():
    if sys.platform != 'win32' or sys.maxsize <= 2**32:
        raise RuntimeError('Build with Windows x64 Python.')
    native()
    licenses()
    icon_and_version()
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    str(ROOT / 'modifier.spec')], cwd=ROOT, check=True)
    package = ROOT / 'dist/Rance10Modifier'
    for name in ['README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md']:
        shutil.copy2(ROOT / name, package / name)
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    archive = release / ('Rance10Modifier-v%s-windows-x64.zip' % VERSION)
    forbidden = {'.asd', '.qnt', '.afa', '.ain', '.ex', '.x'}
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(package.rglob('*')):
            if path.is_file():
                if path.suffix.lower() in forbidden or path.name in ['alice.exe', 'catalog.json', 'manifest.json', 'settings.json', 'operations.jsonl', 'last-error.txt']:
                    raise RuntimeError('Private or game resource in package: ' + str(path))
                output.write(path, path.relative_to(package.parent))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (release / 'SHA256SUMS.txt').write_text(digest + '  ' + archive.name + '\n', encoding='utf-8')
    print('Release:', archive)
    print('SHA256:', digest)


if __name__ == '__main__':
    main()
