$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv-desktop\Scripts\python.exe')) {
    py -3.12 -m venv .venv-desktop
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& .\.venv-desktop\Scripts\python.exe -m pip install -r requirements-desktop.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv-desktop\Scripts\python.exe -m PyInstaller --noconfirm --clean QuaggansHoard.spec
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
Copy-Item -LiteralPath 'WINDOWS.md' -Destination 'dist\QuaggansHoard\START-HERE.md'
Compress-Archive -Path 'dist\QuaggansHoard' -DestinationPath 'dist\QuaggansHoard-Windows.zip' -Force
Write-Output 'Ready: dist\QuaggansHoard-Windows.zip'
