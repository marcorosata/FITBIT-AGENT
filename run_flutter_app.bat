@echo off
setlocal enabledelayedexpansion

echo.
echo =====================================
echo   FLUTTER APP LAUNCHER
echo =====================================
echo.

:: Check if Flutter is installed
where flutter >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Flutter not found!
    echo.
    echo Please:
    echo 1. Extract flutter_windows_3.27.0-stable.zip to C:\
    echo 2. Add C:\flutter\bin to your PATH
    echo 3. Restart this script
    echo.
    pause
    exit /b 1
)

echo [1/4] Flutter found!
flutter --version

echo.
echo [2/4] Navigating to flutter_app...
cd /d "%~dp0flutter_app"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] flutter_app folder not found!
    pause
    exit /b 1
)

echo.
echo [3/4] Installing dependencies...
call flutter pub get
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to get dependencies
    pause
    exit /b 1
)

echo.
echo [4/4] Listing available devices...
call flutter devices

echo.
echo =====================================
echo   READY TO LAUNCH
echo =====================================
echo.
echo Choose your device:
echo   1) Chrome (web browser)
echo   2) Android device (USB connected)
echo   3) Windows desktop
echo.
set /p choice="Enter choice (1-3): "

if "%choice%"=="1" (
    echo.
    echo Launching in Chrome...
    start cmd /k "cd /d %CD% && flutter run -d chrome"
) else if "%choice%"=="2" (
    echo.
    echo Launching on Android device...
    start cmd /k "cd /d %CD% && flutter run"
) else if "%choice%"=="3" (
    echo.
    echo Launching on Windows...
    start cmd /k "cd /d %CD% && flutter run -d windows"
) else (
    echo Invalid choice. Launching in Chrome by default...
    start cmd /k "cd /d %CD% && flutter run -d chrome"
)

echo.
echo App is launching in a new window...
echo You can close this window.
timeout /t 3
exit
