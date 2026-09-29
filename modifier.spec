# Game assets and alice-tools are intentionally excluded.
from pathlib import Path

root = Path(SPECPATH)
analysis = Analysis(
    [str(root / 'app/main.py')],
    pathex=[str(root / 'app')],
    binaries=[(str(root / 'resources/LiveValues.exe'), '.')],
    datas=[(str(root / 'resources/使用说明.txt'), '.'),
           (str(root / 'resources/app.ico'), '.'),
           (str(root / 'resources/licenses'), 'licenses')],
    hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True,
    name='兰斯10修改器', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(root / 'resources/app.ico'), version=str(root / 'resources/version-info.txt'),
)
collect = COLLECT(
    exe, analysis.binaries, analysis.datas,
    strip=False, upx=False, name='Rance10Modifier',
)
