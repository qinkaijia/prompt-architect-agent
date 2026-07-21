#ifndef MyAppVersion
  #define MyAppVersion "0.3.0"
#endif
#ifndef MyVersionInfo
  #define MyVersionInfo "0.3.0.0"
#endif

[Setup]
AppId={{F474A855-6BBE-4B5B-A9A6-2278974F2E34}
AppName=Prompt Architect
AppVersion={#MyAppVersion}
AppPublisher=qinkaijia
AppPublisherURL=https://github.com/qinkaijia/prompt-architect-agent
AppSupportURL=https://github.com/qinkaijia/prompt-architect-agent/issues
DefaultDirName={localappdata}\Programs\Prompt Architect
DefaultGroupName=Prompt Architect
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\release
OutputBaseFilename=Prompt-Architect-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\PromptArchitect.exe
VersionInfoVersion={#MyVersionInfo}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："; Flags: unchecked

[Files]
Source: "..\dist\PromptArchitect\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Prompt Architect"; Filename: "{app}\PromptArchitect.exe"
Name: "{autodesktop}\Prompt Architect"; Filename: "{app}\PromptArchitect.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PromptArchitect.exe"; Description: "启动 Prompt Architect"; Flags: nowait postinstall skipifsilent
