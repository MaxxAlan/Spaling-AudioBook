$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Find-WinGet {
    $command = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $alias = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"
    if (Test-Path -LiteralPath $alias) { return $alias }
    return $null
}

if ([Environment]::OSVersion.Version.Build -lt 17763) {
    throw "WinGet requires Windows 10 1809 build 17763 or newer."
}

$winget = Find-WinGet
if ($winget) {
    Write-Host "[OK] WinGet: $winget"
    exit 0
}

Write-Host "[*] Trying to register the built-in App Installer..."
try {
    Add-AppxPackage `
        -RegisterByFamilyName `
        -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe `
        -ErrorAction Stop
} catch {
    Write-Host "[*] App Installer registration was unavailable; using official repair module."
}

$env:PATH = "$env:PATH;$env:LOCALAPPDATA\Microsoft\WindowsApps"
$winget = Find-WinGet
if (-not $winget) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Install-PackageProvider -Name NuGet -Force -Scope CurrentUser | Out-Null
    Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
    Install-Module -Name Microsoft.WinGet.Client -Force -Repository PSGallery -Scope CurrentUser
    Import-Module Microsoft.WinGet.Client
    Repair-WinGetPackageManager -Force -Latest
    $winget = Find-WinGet
}

if (-not $winget) {
    throw "WinGet could not be installed. App Installer or software installation is blocked by Windows policy."
}

& $winget --info | Out-Null
Write-Host "[OK] WinGet installed: $winget"
