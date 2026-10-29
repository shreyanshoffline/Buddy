; Inno Setup script: turns the Nuitka bundle (build\bundle\Buddy) into a real Windows installer.
; Build:  iscc /DAppVersion=0.9.8 packaging\windows\Buddy.iss        (output: dist\Buddy-Setup-<ver>-x64.exe)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Buddy"
#define AppExe  "Buddy.exe"

[Setup]
; Never change AppId: it is how Windows recognises an upgrade of the same app.
AppId={{6F1E7B52-3C58-4E0B-9A47-5B3D1F6C2A90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Shrey Industries
AppPublisherURL=https://github.com/shreyanshoffline/Buddy
AppSupportURL=https://github.com/shreyanshoffline/Buddy/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installs per-user by default (no admin prompt); the dialog lets people choose all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=Buddy-Setup-{#AppVersion}-x64
SetupIconFile=..\..\build\icons\Buddy.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 64-bit Windows 10 or newer (Windows 11 on ARM runs it through built-in x64 emulation).
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\build\bundle\Buddy\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch Buddy"; Flags: nowait postinstall skipifsilent
