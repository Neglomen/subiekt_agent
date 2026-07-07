; Plik: subiekt_agent/installer/setup.iss
; Skrypt instalatora Inno Setup dla SuppSales Subiekt GT Agent

[Setup]
AppName=SuppSales Subiekt GT Agent
AppVersion=0.5.1
DefaultDirName={userappdata}\SuppSalesAgent
DefaultGroupName=SuppSales Agent
OutputDir=Output
OutputBaseFilename=SuppSalesAgent_Setup
Compression=lzma
SolidCompression=yes
; Ścieżka do ikony instalatora i deinstalatora
SetupIconFile=..\app\gui\assets\icon.png
UninstallDisplayIcon={app}\SuppSalesAgent.exe
; Instalacja w AppData użytkownika nie wymaga uprawnień administratora
PrivilegesRequired=lowest

[Files]
; Kopiujemy wszystkie pliki skompilowane przez PyInstaller z katalogu dist
Source: "..\dist\SuppSalesAgent\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

; Dodatkowo jeśli deweloper ma pliki konfiguracyjne w głównym folderze,
; kopiujemy je do folderu instalacyjnego tylko jeśli tam nie istnieją,
; żeby nie nadpisywać dotychczasowej konfiguracji klienta podczas aktualizacji!
Source: "..\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\.env"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
; Skróty w menu Start i na pulpicie
Name: "{group}\SuppSales Agent"; Filename: "{app}\SuppSalesAgent.exe"; IconFilename: "{app}\app\gui\assets\icon.png"
Name: "{commondesktop}\SuppSales Agent"; Filename: "{app}\SuppSalesAgent.exe"; IconFilename: "{app}\app\gui\assets\icon.png"

[Run]
; Opcja uruchomienia aplikacji zaraz po zakończeniu instalacji
Filename: "{app}\SuppSalesAgent.exe"; Description: "Uruchom SuppSales Agent"; Flags: nowait postinstall skipifsilent
