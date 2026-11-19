; Інсталятор ReCut (Inno Setup 6). Збирає build.sh: ISCC /DAppVersion=1.2.3 installer.iss
; Тека — на вибір користувача, без прав адміністратора: програма пише у свою теку (data, renders), тож потрібен дозвіл на запис.
; Оновлення ставиться в ту саму теку поверх, data й renders лишаються.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F2A5C4E-7B3D-4E1A-9C6F-2D8B0A4E1F37}
AppName=ReCut
AppVersion={#AppVersion}
AppVerName=ReCut {#AppVersion}
AppPublisher=mrbear22
AppPublisherURL=https://github.com/mrbear22/ReCut
AppUpdatesURL=https://github.com/mrbear22/ReCut/releases
DefaultDirName={localappdata}\Programs\ReCut
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=ReCut-Setup
SetupIconFile=launcher\icon.ico
UninstallDisplayIcon={app}\ReCut.exe
UninstallDisplayName=ReCut
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
; програма раніше звалась ShortsMaker: старий запускач і ярлики
Type: files; Name: "{app}\ShortsMaker.exe"
Type: files; Name: "{autoprograms}\ShortsMaker.lnk"
Type: files; Name: "{autodesktop}\ShortsMaker.lnk"

[Files]
Source: "dist\ReCut\*"; DestDir: "{app}"; Excludes: "\data,\renders,__pycache__,*.bat"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\ReCut"; Filename: "{app}\ReCut.exe"
Name: "{autodesktop}\ReCut"; Filename: "{app}\ReCut.exe"; Tasks: desktopicon

[Run]
; і після звичайного встановлення, і після тихого оновлення з програми
Filename: "{app}\ReCut.exe"; Description: "{cm:LaunchProgram,ReCut}"; Flags: nowait postinstall

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
  Probe := AddBackslash(WizardDirValue) + 'recut-write.tmp';
  if ForceDirectories(WizardDirValue) and SaveStringToFile(Probe, '', False) then DeleteFile(Probe)
  else begin
    MsgBox('У цю теку не можна записувати без прав адміністратора. Обери іншу, наприклад на диску D: або у своїй теці користувача.', mbError, MB_OK);
    Result := False;
  end;
end;
