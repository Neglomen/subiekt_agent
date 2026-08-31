; Plik: subiekt_agent/installer/setup.iss
; Skrypt instalatora Inno Setup dla SuppSales Subiekt GT Agent

[Setup]
; AppId to trwała tożsamość aplikacji — po nim Inno rozpoznaje, że to aktualizacja,
; a nie druga równoległa instalacja. Bez niego rolę tę pełni AppName, więc zmiana nazwy
; produktu założyłaby nowy wpis w "Programy i funkcje" obok starego.
; NIE ZMIENIAĆ w kolejnych wydaniach.
AppId={{7C1F0B34-2E58-4A7D-9F3C-1B6A5D40E2C9}
AppName=SuppSales Subiekt GT Agent
; UWAGA: musi być zgodne z APP_VERSION w app/services/updater.py
AppVersion=0.10.0
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

; Restart Manager sam domyka aplikacje trzymające pliki z sekcji [Files]. Nie wystarcza
; to jednak na cloudflared.exe/ngrok.exe: agent pobiera je dopiero w trakcie działania,
; więc nie ma ich w [Files] i RM o nich nie wie. Domyka je sekcja [Code] na końcu pliku.
CloseApplications=yes
RestartApplications=no

; PyInstaller (tryb onedir) trzyma caly runtime w `_internal`. Bez wyczyszczenia tego
; katalogu aktualizacja tylko DOKLADA pliki: modul usuniety albo przemianowany miedzy
; wersjami zostaje obok nowych i paczka robi sie niespojna. Stad brala sie koniecznosc
; odinstalowywania agenta przed instalacja nowej wersji.
; `config.json` i `.env` leza poza `_internal`, wiec konfiguracja klienta to przezywa.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

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
; Skróty w menu Start i na pulpicie.
; {autodesktop}, nie {commondesktop}: ten drugi wskazuje na C:\Users\Public\Desktop,
; gdzie zapis wymaga uprawnień administratora. Przy PrivilegesRequired=lowest instalator
; ich nie ma, więc tworzenie skrótu kończyło się błędem dostępu.
Name: "{group}\SuppSales Agent"; Filename: "{app}\SuppSalesAgentAppV12.exe"; IconFilename: "{app}\app\gui\assets\icon.ico"
Name: "{autodesktop}\SuppSales Agent"; Filename: "{app}\SuppSalesAgentAppV12.exe"; IconFilename: "{app}\app\gui\assets\icon.ico"

[Run]
; Opcja uruchomienia aplikacji zaraz po zakończeniu instalacji
Filename: "{app}\SuppSalesAgentAppV12.exe"; Description: "Uruchom SuppSales Agent"; Flags: nowait postinstall skipifsilent

[Code]
// Domyka procesy uruchomione z katalogu instalacji, zanim instalator ruszy z plikami.
//
// Sam agent to za malo: pobiera on cloudflared.exe / ngrok.exe do {app}\bin i uruchamia
// je jako procesy potomne. Nie ma ich w [Files], wiec Restart Manager ich nie widzi, a
// dopoki zyja, nadpisanie katalogu konczy sie bledem dostepu.
//
// Filtrujemy po SCIEZCE, nie po nazwie obrazu - "taskkill /IM cloudflared.exe" ubilby
// takze tunel niezwiazany z agentem, gdyby uzytkownik mial wlasny.
procedure KillProcessesFromAppDir();
var
  ResultCode: Integer;
  Script: String;
begin
  Script := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' +
            'Get-Process -ErrorAction SilentlyContinue | ' +
            'Where-Object { $_.Path -like ''' + ExpandConstant('{app}') + '\*'' } | ' +
            'Stop-Process -Force -ErrorAction SilentlyContinue"';
  Exec('powershell.exe', Script, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';

  if DirExists(ExpandConstant('{app}')) then
  begin
    KillProcessesFromAppDir();

    // Nazwa pliku agenta jest unikalna, wiec ubicie po niej nie ma skutkow ubocznych.
    // Zostaje jako wyjscie awaryjne, gdyby PowerShell byl zablokowany politykami.
    Exec(ExpandConstant('{cmd}'), '/C taskkill /F /IM SuppSalesAgentAppV12.exe', '',
         SW_HIDE, ewWaitUntilTerminated, ResultCode);

    // Chwila na zwolnienie uchwytow przez system - bez tego pierwsze pliki potrafia
    // byc jeszcze zablokowane w momencie kopiowania.
    Sleep(1500);
  end;
end;
