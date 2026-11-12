; Script generated for SAM VOICE STUDIO
#define MyAppName "SAM DUB - SAM VOICE STUDIO"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "SAM AI Audio Lab"
#define MyAppExeName "SAM_VOICE_STUDIO.exe"

[Setup]
AppId={{E681F08B-D99A-4E15-99F7-7C90F74991B2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SAM VOICE STUDIO
DefaultGroupName=SAM DUB Voice Studio
AllowNoIcons=yes
OutputDir=C:\Users\SAM\Desktop
OutputBaseFilename=SAM_VOICE_STUDIO_Setup
SetupIconFile=C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\app_icon.ico
Compression=lzma2/normal
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
DisableDirPage=no
DisableProgramGroupPage=no
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\SAM_VOICE_STUDIO.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\Launcher.cs"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\voices\*"; DestDir: "{app}\voices"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\Users\SAM\Desktop\SAM-VOICE-STUDIO-main\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\outputs"; Permissions: everyone-full

[Icons]
Name: "{autoprograms}\SAM DUB Voice Studio"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\SAM DUB Voice Studio"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,SAM DUB Voice Studio}"; Flags: nowait postinstall skipifsilent
