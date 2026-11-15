; Інсталятор ShortsMaker (Inno Setup 6). Збирає build.sh: ISCC /DAppVersion=1.2.3 installer.iss
; Ставиться без прав адміністратора в %LOCALAPPDATA%\Programs\ShortsMaker; оновлення ставиться поверх, дані лишаються.
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
DisableDirPage=yes
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
; код і вбудовані бібліотеки — начисто, щоб від старої версії не лишилось зайвих файлів; data не чіпаємо
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\ffmpeg"

[Files]
Source: "dist\ShortsMaker\*"; DestDir: "{app}"; Excludes: "\data\*,\renders\*,__pycache__\*,*.bat"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\ShortsMaker"; Filename: "{app}\ShortsMaker.exe"
Name: "{autodesktop}\ShortsMaker"; Filename: "{app}\ShortsMaker.exe"; Tasks: desktopicon

[Run]
; і після звичайного встановлення, і після тихого оновлення з програми
Filename: "{app}\ShortsMaker.exe"; Description: "{cm:LaunchProgram,ShortsMaker}"; Flags: nowait postinstall

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-Process | Where-Object {{ $_.Path -like '{app}\*' } | Stop-Process -Force"""; Flags: runhidden; RunOnceId: "StopShortsMaker"

[UninstallDelete]
; разом з проєктами, моделями й завантаженим ШІ; готові шорти лишаються у «Відео\ShortsMaker»
Type: filesandordirs; Name: "{app}"
