from PyInstaller.utils.hooks import collect_data_files

a = Analysis(['desktop.py'], pathex=[],
    datas=[('public', 'public'), ('cleanup_rules.json', '.'), ('bifrost.json', '.')] + collect_data_files('webview'),
    hiddenimports=['keyring.backends.Windows'],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tkinter'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='QuaggansHoard',
          icon='public/favicon.ico',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='QuaggansHoard')
