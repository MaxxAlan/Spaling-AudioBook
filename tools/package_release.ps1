param(
    [string]$Version = "0.0.2",
    [string]$OutputDir = ""
)
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDir) { $OutputDir = Join-Path $projectRoot "release" }
$releaseRoot = [IO.Path]::GetFullPath($OutputDir)
if (-not $releaseRoot.StartsWith($projectRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDir must stay inside the project workspace"
}
$payload = Join-Path $releaseRoot "payload"
if (Test-Path -LiteralPath $payload) {
    $resolvedPayload = (Resolve-Path -LiteralPath $payload).Path
    if (-not $resolvedPayload.StartsWith($releaseRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refuse to clean payload outside release directory"
    }
    Remove-Item -LiteralPath $resolvedPayload -Recurse -Force
}
New-Item -ItemType Directory -Path $payload -Force | Out-Null

& pnpm --dir (Join-Path $projectRoot "poster-generator") build
if ($LASTEXITCODE) { throw "Poster generator build failed" }

$excludedDirs = @(
    ".git", ".github", ".venv", ".audiobook-web", ".audiobook-work", ".pytest_cache",
    ".ruff_cache", ".story-thumbnail", "__pycache__", "node_modules", "tests", "testing",
    "examples", "ComfyUI", "output", "artifacts", "projects", "cache", "logs", "temp", "tmp", "release",
    (Join-Path $projectRoot "installer"),
    (Join-Path $projectRoot "models"),
    (Join-Path $projectRoot "poster-generator\src"),
    (Join-Path $projectRoot "audio-comic\assets\voices"),
    (Join-Path $projectRoot "audio-comic\models\voices")
)
$excludedFiles = @(
    "*.md", "*.log", "*.wav", "*.webm", "*.mp3", "*.mp4", "*.part", "*.safetensors",
    "*.ckpt", "*.gguf", "*.bin", "*.pyc", "*.map", ".env", ".env.example", ".gitignore",
    ".install-manifest.json", "custom_voices.json", "ci_smoke.py", "audit_release.py",
    "package_release.ps1", "eslint.config.js", "tsconfig*.json", "pnpm-workspace.yaml"
)
$args = @($projectRoot, $payload, "/S", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD") + $excludedDirs + @("/XF") + $excludedFiles
& robocopy @args | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $payload

& python (Join-Path $projectRoot "tools\audit_release.py") $payload
if ($LASTEXITCODE) { throw "Release audit failed" }

$zip = Join-Path $releaseRoot "Spaling-Audiobook-v$Version-portable.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $payload "*") -DestinationPath $zip -CompressionLevel Optimal

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if ($iscc) {
    & $iscc "/DSourceDir=$payload" "/DAppVersion=$Version" "/DOutputDir=$releaseRoot" (Join-Path $projectRoot "installer\SpalingAudiobook.iss")
    if ($LASTEXITCODE) { throw "Inno Setup failed" }
}

$installer = Join-Path $releaseRoot "Spaling-Audiobook-v$Version-setup.exe"
$thumbprint = [Environment]::GetEnvironmentVariable("SPALING_SIGN_THUMBPRINT")
if ($thumbprint -and (Test-Path -LiteralPath $installer)) {
    $signtool = (Get-Command signtool.exe -ErrorAction Stop).Source
    & $signtool sign /sha1 $thumbprint /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 $installer
    if ($LASTEXITCODE) { throw "Authenticode signing failed" }
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne "Valid") { throw "Installer signature is not valid: $($signature.Status)" }
}

$artifacts = @($zip)
if (Test-Path -LiteralPath $installer) { $artifacts += $installer }
$checksums = $artifacts | ForEach-Object {
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_
    "$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($_))"
}
$checksums | Set-Content -LiteralPath (Join-Path $releaseRoot "SHA256SUMS.txt") -Encoding ascii
Write-Host "Release ready: $releaseRoot"
