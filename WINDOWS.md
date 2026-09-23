# Quaggan's Hoard for Windows

Extract the entire ZIP, then double-click **QuaggansHoard.exe** inside its folder.
Keep the `_internal` folder beside the executable. Python is included; no Python
installation or hosted account is needed. Windows 10/11 x64 and Microsoft Edge
WebView2 Runtime are required. If WebView2 is missing, install Microsoft's Evergreen
Runtime from https://developer.microsoft.com/microsoft-edge/webview2/ .

On first launch, paste a Guild Wars 2 API key with **account, characters,
inventories, and progression** permissions. Create one at
https://account.arena.net/applications . The app checks the key before saving it.

The key is stored in Windows Credential Manager for your Windows user, under
`QuaggansHoard`. It is never included in preferences, the ZIP or browser storage.
The app sends it only to the official GW2 API. Local software running as your
Windows user may still be able to access your credentials. Account settings lets
you replace or forget the saved key; forgetting does not revoke it at ArenaNet.

Character/keep preferences are stored in `%LOCALAPPDATA%\QuaggansHoard\preferences.json`.
The app uses an authenticated server bound only to localhost on a random port;
closing the desktop window stops it. Wiki lookups send item identifiers, not keys.
External links open in your usual browser. Internet access is required for lookups.

This is an unsigned portable build, not an installer. Windows may show an unknown
publisher warning. Releases should be code-signed before broad distribution.
To update, close the app and extract the new release to a fresh folder. Preferences
and credentials are kept outside the app folder. Deleting the folder uninstalls
the app; use Forget saved key first if you also want to remove its credential.

## Building from source

Run `powershell -ExecutionPolicy Bypass -File .\build-windows.ps1` with Python 3.12
on Windows x64. The script uses a local virtual environment and produces
`dist\QuaggansHoard-Windows.zip`. Only explicit public assets/rules are bundled;
`.env`, tests, screenshots and private settings are not included.

For development: `.venv-desktop\Scripts\python.exe desktop.py`.
The original browser mode still runs with `python server.py` and `.env`.
The stable browser baseline is on Git branch `main` and tag `web-baseline`.

Built with pywebview (https://pywebview.flowrl.com/), keyring
(https://keyring.readthedocs.io/), and PyInstaller (https://pyinstaller.org/).
GW2 artwork credits are in `_internal/public/art/SOURCES.md`.
