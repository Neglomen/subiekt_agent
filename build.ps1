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
poetry run pyinstaller --clean subiekt_agent.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "[-] Błąd podczas działania PyInstaller! Przerywam." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "[+] PyInstaller pomyślnie skompilował pliki do katalogu dist\SuppSalesAgent." -ForegroundColor Green

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
    Write-Host "    Paczka plików działa i znajduje się w katalogu dist\SuppSalesAgent" -ForegroundColor Yellow
    Write-Host "    Aby zbudować instalator instalacyjny .exe, pobierz i zainstaluj Inno Setup 6" -ForegroundColor Yellow
    Write-Host "    z adresu: https://jrsoftware.org/" -ForegroundColor Yellow
}

Write-Host "==================================================" -ForegroundColor Cyan
