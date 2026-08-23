# Plik: subiekt_agent/build.ps1
# Skrypt PowerShell do kompilacji PyInstaller i budowania instalatora Inno Setup

# Zmiana kodowania konsoli na UTF-8 dla ładnych komunikatów PL
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   SuppSales Agent - Skrypt Budowania Paczki" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Sprawdzenie ścieżki do kompilatora Inno Setup
$innoPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $innoPath)) {
    $innoPath = "C:\Program Files\Inno Setup 6\ISCC.exe"
}

# 2. Uruchomienie kompilacji PyInstaller
Write-Host "[1/2] Kompilacja kodu do wersji wykonywalnej (PyInstaller)..." -ForegroundColor Yellow
poetry run pyinstaller --clean -y subiekt_agent.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "[-] Błąd podczas działania PyInstaller! Przerywam." -ForegroundColor Red
    exit $LASTEXITCODE
}
# UWAGA: .env i config.json CELOWO nie trafiają do paczki.
#  * .env zawiera hasło operatora Sfery, klucz API agenta oraz tokeny Cloudflare/ngrok,
#    a release na GitHubie jest publiczny — instalator Inno Setup rozpakowuje się
#    zwykłym archiwizerem, więc wszystko w nim jest do odczytania przez każdego.
#    Agent bez .env startuje na wartościach domyślnych (SferaSettings w app/config.py)
#    i konfiguruje się przez panel GUI, który zapisuje .env na miejscu.
#  * config.json instaluje Inno Setup z flagą onlyifdoesntexist, żeby aktualizacja
#    nie nadpisała mapowań towarów na komputerze klienta kopią z maszyny budującej.
Write-Host "[+] Usuwanie plików konfiguracyjnych z paczki (nie mogą trafić do publicznego instalatora)..." -ForegroundColor Yellow
foreach ($leftover in @("dist\SuppSalesAgentAppV12\.env", "dist\SuppSalesAgentAppV12\config.json")) {
    if (Test-Path $leftover) {
        Remove-Item -Path $leftover -Force
        Write-Host "    - usunieto $leftover" -ForegroundColor DarkGray
    }
}
Write-Host "[+] PyInstaller pomyślnie skompilował pliki do katalogu dist\SuppSalesAgentAppV12." -ForegroundColor Green

# 3. Uruchomienie kompilacji Inno Setup
if (Test-Path $innoPath) {
    Write-Host "[2/2] Budowanie instalatora (.exe) przy użyciu Inno Setup..." -ForegroundColor Yellow
    & $innoPath installer\setup.iss
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[-] Błąd podczas działania Inno Setup!" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "[+] Sukces! Instalator został wygenerowany w:" -ForegroundColor Green
    Write-Host "    installer\Output\SuppSalesAgent_Setup.exe" -ForegroundColor Cyan
} else {
    Write-Host "[!] Ostrzeżenie: Nie znaleziono Inno Setup 6 (ISCC.exe) w systemie." -ForegroundColor Yellow
    Write-Host "    Paczka plików działa i znajduje się w katalogu dist\SuppSalesAgentAppV12" -ForegroundColor Yellow
    Write-Host "    Aby zbudować instalator instalacyjny .exe, pobierz i zainstaluj Inno Setup 6" -ForegroundColor Yellow
    Write-Host "    z adresu: https://jrsoftware.org/" -ForegroundColor Yellow
}

Write-Host "==================================================" -ForegroundColor Cyan
