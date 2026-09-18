; Inno Setup Installer Script - Dy-Sentry
; Usage: compile with Inno Setup 6, or run build.bat / GitHub Actions CI
;
; Prerequisites:
;   1. PyInstaller build completed (dist\dy-sentry\)
;   2. Inno Setup 6 installed (https://jrsoftware.org/isdl.php)

#define MyAppName "Dy-Sentry"
; 允许 CI 通过 iscc /DMyAppVersion=x.y.z 覆盖；本地手动编译时回退到 0.1.0
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Dy-Sentry"
#define MyAppURL "https://github.com/tempdave119/Dy-Sentry"
#define MyAppExeName "dy-sentry.exe"

[Setup]
AppId={{C1A2B3D4-E5F6-7890-ABCD-1234567890AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Output
OutputDir=installer_output
OutputBaseFilename=Dy-Sentry-v{#MyAppVersion}-Setup
Compression=lzma2/ultra64
SolidCompression=yes

; Install directory (user's AppData - no admin needed, program can write freely)
DefaultDirName={localappdata}\Dy-Sentry
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; Other
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; PyInstaller build output
Source: "dist\dy-sentry\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Launcher
Source: "launcher.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 开始菜单快捷方式
Name: "{group}\启动 Dy-Sentry"; Filename: "{app}\launcher.bat"; WorkingDir: "{app}"; Comment: "启动服务并打开预览页"
Name: "{group}\录制文件目录"; Filename: "{app}\recordings"; Comment: "打开录制文件保存目录"
Name: "{group}\配置目录"; Filename: "{app}\config"; Comment: "打开配置文件目录"
Name: "{group}\卸载"; Filename: "{uninstallexe}"
; 桌面快捷方式
Name: "{autodesktop}\Dy-Sentry"; Filename: "{app}\launcher.bat"; WorkingDir: "{app}"; Comment: "启动 Dy-Sentry 并打开预览页"

[Dirs]
Name: "{app}\recordings"
Name: "{app}\config"

[Run]
Description: "启动 Dy-Sentry"; Filename: "{app}\launcher.bat"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\recordings"
Type: filesandordirs; Name: "{app}\config"
Type: filesandordirs; Name: "{app}\__pycache__"
