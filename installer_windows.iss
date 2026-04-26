; installer_windows.iss - Inno Setup script
; Gera instalador com destino padrao em C:\Program Files\Music Auto Manager
; e cria atalho no menu iniciar e opcional na area de trabalho.

#define MyAppName "Music Auto Manager"
#define MyAppExeName "MusicAutoManager.exe"
#define MyAppVersion "1.0.8"
#define MyPublisher "Jesse / CARMBA"

[Setup]
AppId={{A5EE0F4F-16EA-4D64-B7D8-4A5E5E6C8F61}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
DefaultDirName={autopf}\Music Auto Manager
DefaultGroupName=Music Auto Manager
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=MusicAutoManager-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
SetupLogging=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "portuguesebrazil"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Files]
Source: "dist\MusicAutoManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent
