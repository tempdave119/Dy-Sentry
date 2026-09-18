@echo off
chcp 65001 >nul 2>&1
REM Build script - Windows (PyInstaller + Inno Setup)
REM Usage: double-click or run in CMD
REM
REM Prerequisites:
REM   Python 3.12 installed (pip available)
REM   Inno Setup 6 installed (optional, for generating installer)
REM
REM Output:
REM   dist\dy-sentry\          - standalone executable directory
REM   installer_output\        - installer package (if Inno Setup installed)

echo ======================================
echo   Dy-Sentry - Build Script (Windows)
echo ======================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.12+
    echo   Download: https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during install
    pause
    exit /b 1
)

REM ================================================================
REM Step 1: Check Python dependencies
REM ================================================================
echo [1/5] Checking Python dependencies...
python -c "import PyInstaller" 2>nul || pip install pyinstaller --quiet
pip install -r requirements.txt --quiet
echo   Dependencies OK

REM ================================================================
REM Step 2: Check/download ffmpeg
REM ================================================================
echo [2/5] Checking ffmpeg...

if exist "bin\ffmpeg.exe" (
    echo   Using local ffmpeg: bin\ffmpeg.exe
    goto :ffmpeg_ok
)

if defined FFMPEG_BIN (
    if exist "%FFMPEG_BIN%" (
        echo   Using FFMPEG_BIN: %FFMPEG_BIN%
        goto :ffmpeg_ok
    )
)

where ffmpeg >nul 2>nul
if not errorlevel 1 (
    echo   Using system ffmpeg
    goto :ffmpeg_ok
)

echo   Downloading ffmpeg for Windows...
if not exist "bin" mkdir bin
echo   URL: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
powershell -Command "& { $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'bin\ffmpeg-download.zip' }"
if errorlevel 1 (
    echo   [WARN] Auto-download failed. Please download ffmpeg manually:
    echo   https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
    echo   Extract and put ffmpeg.exe into the bin\ folder.
    goto :ffmpeg_skip
)
echo   Extracting...
powershell -Command "& { Expand-Archive -Path 'bin\ffmpeg-download.zip' -DestinationPath 'bin\ffmpeg-temp' -Force }"
for /r "bin\ffmpeg-temp" %%f in (ffmpeg.exe) do (
    copy "%%f" "bin\ffmpeg.exe" >nul
    echo   Extracted: bin\ffmpeg.exe
    goto :ffmpeg_extracted
)
:ffmpeg_extracted
del /q "bin\ffmpeg-download.zip" 2>nul
rmdir /s /q "bin\ffmpeg-temp" 2>nul
if not exist "bin\ffmpeg.exe" (
    echo   [WARN] ffmpeg.exe not found after extraction
    goto :ffmpeg_skip
)
goto :ffmpeg_ok

:ffmpeg_skip
echo   [INFO] Build output will NOT include ffmpeg (video recording disabled)
:ffmpeg_ok

REM ================================================================
REM Step 3: PyInstaller build
REM ================================================================
echo [3/5] Building with PyInstaller...
pyinstaller dy-sentry.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    pause
    exit /b 1
)
if not exist "dist\dy-sentry\dy-sentry.exe" (
    echo [ERROR] Build output not found: dist\dy-sentry\dy-sentry.exe
    pause
    exit /b 1
)
echo   PyInstaller build OK

REM ================================================================
REM Step 4: Inno Setup (optional)
REM ================================================================
echo [4/5] Checking Inno Setup...
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if not defined ISCC (
    echo.
    echo   [INFO] Inno Setup 6 not found, skipping installer generation
    echo   To create an installer, download Inno Setup from:
    echo   https://jrsoftware.org/isdl.php
    echo.
    echo ======================================
    echo   Build complete!
    echo ======================================
    echo.
    echo   Output:    dist\dy-sentry\
    echo   Executable: dist\dy-sentry\dy-sentry.exe
    echo.
    echo   You can copy this folder to any Windows PC and run dy-sentry.exe.
    echo.
    pause
    exit /b 0
)

echo   Found Inno Setup: %ISCC%
echo   Building installer...
"%ISCC%" installer.iss
if errorlevel 1 (
    echo   [ERROR] Inno Setup compilation failed
    pause
    exit /b 1
)

echo.
echo ======================================
echo   Build complete!
echo ======================================
echo.
echo   Output:     dist\dy-sentry\
echo   Installer:  installer_output\
echo.
pause
