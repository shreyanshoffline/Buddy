#define AppName "Buddy"
#ifndef AppVersion
  #define AppVersion "0.9.8"
#endif
#define AppPublisher "Buddy"
#define AppExeName "Buddy.exe"

[Setup]
AppId={{6CE4A6C2-3E53-4A1B-8A0B-4C3C72CB2D99}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Buddy
DefaultGroupName=Buddy
OutputDir=..\..\dist
OutputBaseFilename=Buddy-Setup-{#AppVersion}-x64
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\build\icons\Buddy.ico
UninstallDisplayIcon={app}\{#AppExeName}
PrivilegesRequired=admin

[Files]
Source: "..\..\build\nuitka\Buddy.dist\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Buddy"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Buddy"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Buddy"; Flags: nowait postinstall skipifsilent
