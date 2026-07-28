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
Write-Host "[1/4] Dang dung ComfyUI server..." -ForegroundColor Cyan
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*ComfyUI*"
} | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "[2/4] Dang xoa Ollama models..." -ForegroundColor Cyan
$ollamaModels = Join-Path $env:USERPROFILE ".ollama\models"
if (Test-Path $ollamaModels) {
    $size = (Get-ChildItem -Recurse $ollamaModels | Measure-Object -Property Length -Sum).Sum / 1GB
    Write-Host "  Tim thay Ollama models: $([math]::Round($size, 1)) GB" -ForegroundColor Yellow
    $removeOllama = Read-Host "  Xoa Ollama models? (y/n)"
    if ($removeOllama -eq "y") {
        Remove-Item -Recurse -Force $ollamaModels
        Write-Host "  Da xoa: Ollama models" -ForegroundColor Gray
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
