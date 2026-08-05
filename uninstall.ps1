#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Xoa toan bo Spaling Audiobook
.DESCRIPTION
    Xoa tat ca: source code, models, venv, data, ComfyUI, Ollama models
.NOTES
    Chay voi quyen Admin: Right-click -> Run with PowerShell
#>

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "========================================" -ForegroundColor Red
Write-Host "   XOA TOAN BO SPALING AUDIOBOOK" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Red
Write-Host ""
Write-Host "Thu muc: $Root" -ForegroundColor Yellow
Write-Host ""

# Confirm
$confirm = Read-Host "Ban co chac muon xoa TOAN BO? (YES de xac nhan)"
if ($confirm -ne "YES") {
    Write-Host "Huy bo." -ForegroundColor Gray
    exit 0
}

Write-Host ""
Write-Host "[1/4] Dang dung cac server local..." -ForegroundColor Cyan
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*ComfyUI*"
} | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

Write-Host "[2/4] Dang xoa model va cache trong o app..." -ForegroundColor Cyan
$localData = Join-Path $Root ".data"
if (Test-Path $localData) {
    $size = (Get-ChildItem -Recurse $localData | Measure-Object -Property Length -Sum).Sum / 1GB
    Write-Host "  Tim thay model/cache (.data): $([math]::Round($size, 1)) GB" -ForegroundColor Yellow
    $removeData = Read-Host "  Xoa model va cache? (y/n)"
    if ($removeData -eq "y") {
        Remove-Item -Recurse -Force $localData
        Write-Host "  Da xoa: $localData" -ForegroundColor Gray
    }
}

Write-Host "[3/4] Dang xoa toan bo thu muc app..." -ForegroundColor Cyan
if (Test-Path $Root) {
    Remove-Item -Recurse -Force $Root
    Write-Host "  Da xoa: $Root" -ForegroundColor Gray
}

Write-Host "[4/4] Hoan tat..." -ForegroundColor Cyan

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   DA XOA TOAN BO!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "De cai dat lai, clone tu GitHub:" -ForegroundColor White
Write-Host "  git clone https://github.com/maxxalan/Spaling-AudioBook.git" -ForegroundColor Gray
Write-Host "  cd Spaling-AudioBook" -ForegroundColor Gray
Write-Host "  .\install.bat" -ForegroundColor Gray
Write-Host ""

pause
