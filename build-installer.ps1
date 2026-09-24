param(
    [ValidatePattern('^\d+\.\d+\.\d+(?:\.\d+)?$')]
    [string]$Version = '0.0.0',
    [switch]$SkipApplicationBuild
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not $SkipApplicationBuild) {
    & "$PSScriptRoot\build-windows.ps1"
    if ($LASTEXITCODE -ne 0) { throw 'Application packaging failed.' }
}

$compilerCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:LOCALAPPDATA} 'Programs\Inno Setup 6\ISCC.exe')
)
$compiler = $compilerCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $compiler) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $compiler = $command.Source }
}
if (-not $compiler) {
    throw 'Inno Setup 6 was not found. Install it with: winget install --id JRSoftware.InnoSetup --exact'
}
if (-not (Test-Path -LiteralPath 'dist\QuaggansHoard\QuaggansHoard.exe')) {
    throw 'The packaged application is missing. Run build-windows.ps1 first.'
}

& $compiler "/DAppVersion=$Version" 'installer\QuaggansHoard.iss'
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }

$installer = "dist\QuaggansHoard-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer was not created: $installer" }
Write-Output "Ready: $installer"
