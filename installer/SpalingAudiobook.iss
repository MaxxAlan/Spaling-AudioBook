#ifndef SourceDir
  #define SourceDir "..\release\payload"
#endif
#ifndef AppVersion
  #define AppVersion "0.0.2"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

[Setup]
AppId={{8A5B8D57-B588-4DDC-9B9C-F14C93EC6841}
AppName=Spaling Audiobook
AppVersion={#AppVersion}
AppPublisher=Spaling Audiobook
DefaultDirName={localappdata}\Programs\SpalingAudiobook
DefaultGroupName=Spaling Audiobook
OutputDir={#OutputDir}
OutputBaseFilename=Spaling-Audiobook-v{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\audiobook.bat

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Spaling Audiobook"; Filename: "{app}\audiobook.bat"; Parameters: "web"; WorkingDir: "{app}"
Name: "{autodesktop}\Spaling Audiobook"; Filename: "{app}\audiobook.bat"; Parameters: "web"; WorkingDir: "{app}"

[Run]
Filename: "{app}\install.bat"; Description: "Cài dependency và model AI (cần khoảng 35 GB)"; Flags: postinstall nowait skipifsilent
