; Inno Setup recipe: turns the PyInstaller build (dist\RaycastGame\) into one installer, dist\RaycastGameSetup.exe.
;
;     uv run pyinstaller raycast-game.spec --noconfirm
;     ISCC packaging\installer.iss
;
; (Inno Setup 6: winget install JRSoftware.InnoSetup; ISCC.exe is in its folder.) It installs for the player only, in
; %LOCALAPPDATA%\Programs\RaycastGame - no administrator prompt, and the map editor can save maps next to the game,
; which it could not under Program Files. Start menu shortcuts for the game and the editor, an optional desktop
; shortcut and an uninstaller come with it. Not needed for Steam, which installs the build folder itself.

#define AppName "Raycast Game"
; AppVersion: keep in step with pyproject.toml
#define AppVersion "0.1.0"
#define Build "..\dist\RaycastGame"

[Setup]
AppId={{4832B085-E88F-446B-AA6B-170382C2E991}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Nathan Loewenthal
PrivilegesRequired=lowest
DefaultDirName={autopf}\RaycastGame
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=RaycastGameSetup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\RaycastGame.exe
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole build folder (a steam_appid.txt copied in by hand is left out: the game tells Steam its app id itself).
Source: "{#Build}\*"; DestDir: "{app}"; Excludes: "steam_appid.txt"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\RaycastGame.exe"
Name: "{group}\{#AppName} Map Editor"; Filename: "{app}\RaycastEditor.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\RaycastGame.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RaycastGame.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
