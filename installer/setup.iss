; Plik: subiekt_agent/installer/setup.iss
; Skrypt instalatora Inno Setup dla SuppSales Subiekt GT Agent

[Setup]
AppName=SuppSales Subiekt GT Agent
; UWAGA: musi być zgodne z APP_VERSION w app/services/updater.py
AppVersion=0.9.0
DefaultDirName={userappdata}\SuppSalesAgent
DefaultGroupName=SuppSales Agent
OutputDir=Output
OutputBaseFilename=SuppSalesAgent_Setup
Compression=lzma
SolidCompression=yes
; Ścieżka do ikony instalatora i deinstalatora
SetupIconFile=..\app\gui\assets\icon.ico
UninstallDisplayIcon={app}\SuppSalesAgentAppV12.exe
; Instalacja w AppData użytkownika nie wymaga uprawnień administratora
PrivilegesRequired=lowest

[Files]
; Kopiujemy wszystkie pliki skompilowane przez PyInstaller z katalogu dist
Source: "..\dist\SuppSalesAgentAppV12\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

; Dodatkowo jeśli deweloper ma pliki konfiguracyjne w głównym folderze,
; kopiujemy je do folderu instalacyjnego tylko jeśli tam nie istnieją,
; żeby nie nadpisywać dotychczasowej konfiguracji klienta podczas aktualizacji!
Source: "..\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
; .env NIE jest pakowany — zawiera sekrety, a release jest publiczny.
; Agent tworzy go sam przy pierwszym zapisie ustawień w panelu GUI.

[Icons]
; Skróty w menu Start i na pulpicie
Name: "{group}\SuppSales Agent"; Filename: "{app}\SuppSalesAgentAppV12.exe"; IconFilename: "{app}\app\gui\assets\icon.ico"
Name: "{commondesktop}\SuppSales Agent"; Filename: "{app}\SuppSalesAgentAppV12.exe"; IconFilename: "{app}\app\gui\assets\icon.ico"

[Run]
; Opcja uruchomienia aplikacji zaraz po zakończeniu instalacji
Filename: "{app}\SuppSalesAgentAppV12.exe"; Description: "Uruchom SuppSales Agent"; Flags: nowait postinstall skipifsilent
