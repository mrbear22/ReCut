; Інсталятор ShortsMaker (Inno Setup 6). Збирає build.sh: ISCC /DAppVersion=1.2.3 installer.iss
; Тека — на вибір користувача, без прав адміністратора: програма пише у свою теку (data, renders), тож потрібен дозвіл на запис.
; Оновлення ставиться в ту саму теку поверх, data й renders лишаються.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F2A5C4E-7B3D-4E1A-9C6F-2D8B0A4E1F37}
AppName=ShortsMaker
AppVersion={#AppVersion}
AppVerName=ShortsMaker {#AppVersion}
AppPublisher=mrbear22
AppPublisherURL=https://github.com/mrbear22/ShortsMaker
AppUpdatesURL=https://github.com/mrbear22/ShortsMaker/releases
DefaultDirName={localappdata}\Programs\ShortsMaker
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=ShortsMaker-Setup
SetupIconFile=launcher\icon.ico
UninstallDisplayIcon={app}\ShortsMaker.exe
UninstallDisplayName=ShortsMaker
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Languages]
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; код і вбудований Python — начисто, щоб від старої версії не лишилось зайвих файлів; data, renders і завантажений ffmpeg не чіпаємо
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\runtime"

[Files]
Source: "dist\ShortsMaker\*"; DestDir: "{app}"; Excludes: "\data,\renders,__pycache__,*.bat"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\ShortsMaker"; Filename: "{app}\ShortsMaker.exe"
Name: "{autodesktop}\ShortsMaker"; Filename: "{app}\ShortsMaker.exe"; Tasks: desktopicon

[Run]
; і після звичайного встановлення, і після тихого оновлення з програми
Filename: "{app}\ShortsMaker.exe"; Description: "{cm:LaunchProgram,ShortsMaker}"; Flags: nowait postinstall

[UninstallRun]
; програма й її вікно Edge (профіль вікна лежить у data\window), інакше теку не видалити
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -like '{app}\*' -or $_.CommandLine -like '*{app}\data\window*' } | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden waituntilterminated; RunOnceId: "StopShortsMaker"

[UninstallDelete]
; проєкти, завантажені ffmpeg, бібліотеки, моделі й ШІ; готові шорти в renders лишаються
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\ffmpeg"
Type: filesandordirs; Name: "{app}\app"

[Code]
// тека без дозволу на запис (наприклад, Program Files) не підходить: програма зберігає туди шорти й проєкти
function NextButtonClick(CurPageID: Integer): Boolean;
var Probe: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then Exit;
  Probe := AddBackslash(WizardDirValue) + 'shortsmaker-write.tmp';
  if ForceDirectories(WizardDirValue) and SaveStringToFile(Probe, '', False) then DeleteFile(Probe)
  else begin
    MsgBox('У цю теку не можна записувати без прав адміністратора. Обери іншу, наприклад на диску D: або у своїй теці користувача.', mbError, MB_OK);
    Result := False;
  end;
end;
