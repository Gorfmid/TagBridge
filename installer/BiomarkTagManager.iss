; Biomark Tag Manager installer
; Prompts: install for all users (Program Files, requires UAC) or current user only (no elevation)

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define MyAppName "Biomark Tag Manager"
#define MyAppPublisher "Biomark"
#define MyAppExeName "BiomarkTagManager.exe"
#define BuildDir "..\dist\BiomarkTagManager"
#define DirAllUsers "{autopf}\Biomark\TagManager"
#define DirCurrentUser "{localappdata}\Biomark\TagManager"

[Setup]
AppId={{B4E8A1C2-6D3F-4A9E-9B1C-7E5F2D8A0C4E}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={code:GetInstallDir}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Biomark TagManager Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Start without elevation; ask on Welcome page (see PrivilegesRequiredOverridesAllowed)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
; Allow standard users to write tags/logs when installed for all users under Program Files
Name: "{app}\tags"; Permissions: users-modify; Check: IsAllUsersInstall
Name: "{app}\logs"; Permissions: users-modify; Check: IsAllUsersInstall
Name: "{app}\tags"; Check: not IsAllUsersInstall
Name: "{app}\logs"; Check: not IsAllUsersInstall

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel2=Choose who this app is for on the next screen:%n%n• All users — installs to Program Files (administrator approval required)%n• Current user only — no administrator rights;%n  installs under your AppData folder%n%nTags and logs are saved in subfolders of the install location.

[Code]
function IsAllUsersInstall: Boolean;
begin
  Result := IsAdminInstallMode;
end;

function GetInstallDir(Param: String): String;
begin
  if IsAdminInstallMode then
    Result := ExpandConstant('{#DirAllUsers}')
  else
    Result := ExpandConstant('{#DirCurrentUser}');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then
    WizardForm.DirEdit.Text := GetInstallDir('');
end;
