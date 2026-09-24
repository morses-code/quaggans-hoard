import os
import sys
from PyInstaller.utils.hooks import collect_data_files

is_windows = sys.platform == 'win32'
is_macos = sys.platform == 'darwin'
icon = 'public/favicon.ico' if is_windows else 'public/quaggan.icns' if is_macos else 'public/quaggan-512.png'
hidden = ['keyring.backends.Windows'] if is_windows else ['keyring.backends.macOS'] if is_macos else ['keyring.backends.SecretService']
app_version = os.environ.get('APP_VERSION', '0.0.0')

a = Analysis(['desktop.py'], pathex=[],
    datas=[('public', 'public')] + collect_data_files('webview'),
    hiddenimports=hidden,
    excludes=(['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tkinter'] if not sys.platform.startswith('linux') else ['PyQt5', 'PySide2', 'PySide6', 'tkinter']),
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='QuaggansHoard',
          icon=icon,
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='QuaggansHoard')

if is_macos:
    app = BUNDLE(coll, name="Quaggan's Hoard.app", icon=icon,
                 bundle_identifier='com.morsescode.quagganshoard',
                 version=app_version,
                 info_plist={'NSPrincipalClass': 'NSApplication', 'NSHighResolutionCapable': True})
