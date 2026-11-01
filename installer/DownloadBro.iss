; Установщик «DownloadBro» для Inno Setup 6 — https://jrsoftware.org/isdl.php
;
; Порядок такой:
;   1) .venv\Scripts\python.exe tools\release.py        — собирает exe и папку release\DownloadBro-<версия>-win64
;   2) "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DownloadBro.iss
; На выходе: release\DownloadBro-<версия>-setup.exe
;
; Без установщика релиз тоже самодостаточен: DownloadBro-<версия>-win64.zip распаковывается в любую
; папку и запускается двойным кликом — установщик нужен только для ярлыков и «Установить/Удалить».

#define MyAppName "DownloadBro"
#include "version.inc"
#define MyAppExeName "DownloadBro.exe"
#define Root AddBackslash(SourcePath) + ".."
#define PortPrefix Root + "\release\" + MyAppName + "-" + MyAppVersion + "-win64"
#define FullDir PortPrefix + "-ffmpeg"
#define LiteDir PortPrefix

; Если есть собранный вариант с ffmpeg — ставим его (офлайн), иначе лёгкий
#if FileExists(FullDir + "\" + MyAppExeName)
  #define PortDir FullDir
#else
  #define PortDir LiteDir
#endif
#if FileExists(PortDir + "\" + MyAppExeName) == False
  #error Сначала соберите релиз: python tools\release.py — нет release\DownloadBro-<версия>-win64\DownloadBro.exe
#endif

[Setup]
; AppId не менять: по нему Windows понимает, что это та же программа, а не новая
AppId={{8E4C1B7A-52F3-4C6E-9B0D-7A5E1D2C4F93}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Den4dev
AppPublisherURL=https://github.com/den4dev/downloadbro
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
SetupIconFile={#Root}\assets\icon.ico
OutputDir={#Root}\release
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Установка без прав администратора: программа пишется в профиль пользователя
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
DisableWelcomePage=no

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "{#PortDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Настройки и история живут в профиле, а не в {app} — спросим, чистить ли их следом
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Answer: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if FileExists(ExpandConstant('{userappdata}\{#MyAppName}\config.json')) then
    begin
      Answer := MsgBox('Удалить настройки и историю {#MyAppName}?', mbConfirmation, MB_YESNO);
      if Answer = IDYES then
      begin
        DelTree(ExpandConstant('{userappdata}\{#MyAppName}'), True, True, True);
        DelTree(ExpandConstant('{localappdata}\{#MyAppName}'), True, True, True);
      end;
    end;
  end;
end;
