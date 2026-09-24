# Quaggan's Hoard for Windows

For the simplest setup, download `QuaggansHoard-Setup-<version>.exe` from the
GitHub release and run it. The per-user installer needs no administrator access,
creates a Start Menu shortcut, offers an optional desktop shortcut, and includes
an uninstaller. The portable ZIP remains available: extract the entire ZIP, then
double-click **QuaggansHoard.exe** inside its folder.
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

The current installer and portable executable are unsigned, so Windows may show an
unknown publisher warning. Releases should be code-signed before broad distribution.
Running a newer installer upgrades the application in place. Preferences and
credentials are kept outside the installation folder, including after uninstall.
Use Forget saved key before uninstalling if you also want to remove its credential.

## Building from source

Run `powershell -ExecutionPolicy Bypass -File .\build-windows.ps1` with Python 3.12
on Windows x64. The script uses a local virtual environment and produces
`dist\QuaggansHoard-Windows.zip`. Install Inno Setup 6, then run
`powershell -ExecutionPolicy Bypass -File .\build-installer.ps1 -Version 1.0.0`
to also produce `dist\QuaggansHoard-Setup-1.0.0.exe`. Only explicit public assets/rules are bundled;
`.env`, tests, screenshots and private settings are not included.

For development: `.venv-desktop\Scripts\python.exe desktop.py`.
The original browser mode still runs with `python server.py` and `.env`.
The stable browser baseline is on Git branch `main` and tag `web-baseline`.

## Publishing a GitHub release

Push a semantic version tag such as `v1.0.0`. The Windows release workflow runs
the tests, builds both formats, silently installs and launches the installer build,
uninstalls it, then creates or updates that tag's GitHub release with:

- `QuaggansHoard-Setup-1.0.0.exe` for normal installation
- `QuaggansHoard-Windows.zip` for portable use

The workflow can also be run manually to test a version. Manual runs store both
files as workflow artifacts but do not create a public release. GitHub Actions must
be enabled and the workflow needs its declared `contents: write` permission.

## Shared development and icons

Browser and desktop modes share `public/app.js`, the HTML/CSS, and Python inventory
logic. After merging into main, develop common features once on feature branches;
rebuild the Windows ZIP to deliver them to desktop users. `desktop.py` and
`public/desktop.js` handle only the Windows shell, credentials and preferences.

`public/quaggan.svg` is the shared header/favicon artwork. `public/favicon.ico`
provides seven resolutions for the executable, window and browser fallback.
After changing the SVG, run `build-icons.py` with `resvg_py==0.5.0` installed,
then rebuild the Windows package. Normal builds use the committed icon files.

Built with pywebview (https://pywebview.flowrl.com/), keyring
(https://keyring.readthedocs.io/), and PyInstaller (https://pyinstaller.org/).
GW2 artwork credits are in `_internal/public/art/SOURCES.md`.

For legendary vendor currency comparisons, also enable wallet permission on your API key. Without it, currency balances display as unknown; inventory scanning still works.
