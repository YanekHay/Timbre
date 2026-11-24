; Inno Setup script for Timbre. Built by packaging\build.ps1.
; Per-user install: no administrator rights needed.

#define AppName "Timbre"
#define AppVersion "0.2.0"

[Setup]
AppId={{6A0C9E3B-7C51-4C3E-9B0E-2F8D6B1E7A41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Timbre
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Timbre-Setup-{#AppVersion}
SetupIconFile=timbre.ico
UninstallDisplayIcon={app}\Timbre.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Timbre\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Timbre.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Timbre.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Timbre.exe"; Description: "Launch Timbre"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Timbre');
    { Only ever delete user data on an explicit "Yes" in an interactive uninstall.
      Silent uninstalls (and suppressed message boxes) always keep it. }
    if DirExists(DataDir) and not UninstallSilent() then
      if SuppressibleMsgBox('Also remove Timbre''s compute runtimes, downloaded model, saved voices, profiles and history?' + #13#10 +
                '(' + DataDir + ', can be several GB. Your generated audio files are not touched.)',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
