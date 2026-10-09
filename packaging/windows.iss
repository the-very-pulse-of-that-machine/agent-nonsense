#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef SourceDir
  #error SourceDir is required
#endif
#ifndef OutputPath
  #error OutputPath is required
#endif

[Setup]
AppId={{D3F00F0B-7276-4840-AAF8-97FA9CFBDB73}
AppName=Doupi 豆皮
AppVersion={#AppVersion}
AppPublisher=Agent Nonsense contributors
AppPublisherURL=https://github.com/wahahaha-cpu/agent-nonsense
DefaultDirName={localappdata}\Programs\Doupi
DefaultGroupName=Doupi 豆皮
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=Doupi-{#AppVersion}-windows-x64-setup
SetupIconFile={#SourceDir}\_internal\agent_nonsense\desktop\assets\agent-nonsense.ico
UninstallDisplayIcon={app}\Doupi.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Doupi 豆皮"; Filename: "{app}\Doupi.exe"
Name: "{autodesktop}\Doupi 豆皮"; Filename: "{app}\Doupi.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Doupi.exe"; Description: "Launch Doupi 豆皮"; Flags: nowait postinstall skipifsilent
