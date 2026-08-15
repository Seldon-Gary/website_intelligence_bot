# Запуск Telegram-бота (терминал 2)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "venv не найден. Создай: python -m venv venv" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path ".\.env")) {
    Write-Host ".env не найден. Скопируй .env.example в .env и заполни." -ForegroundColor Red
    exit 1
}

. .\venv\Scripts\Activate.ps1
python -m bot.main
